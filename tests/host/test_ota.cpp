#include "ota_stubs.hpp"
#include "ota_under_test.inc"

static AtModem modem;
static void (*scheduled_task)(void *);
static int task_count, abort_count, end_count, boot_count, restart_count, lock_depth;
static bool fail_task, corrupt_chunk;
static call_state_t fake_state = CALL_STATE_IDLE;
static std::string written;
static esp_partition_t partition{"ota_1", 0x390000, 0x380000};

namespace Network4g { AtModem *GetModemInstance() { return &modem; } }
bool AtUart::SendCommand(const std::string& command, int timeout) {
    if (command.find("AT+MHTTPCREATE=") == 0) {
        callbacks.front()("MHTTPCREATE", {0});
    } else if (command.find("AT+MHTTPREQUEST=") == 0) {
        callbacks.front()("MHTTPURC", {std::string("header"), 0, 200, 19, std::string("Content-Length: 3\r\n")});
        callbacks.front()("MHTTPURC", {std::string("content"), 0, 3, 1, 1, std::string("61")});
        callbacks.front()("MHTTPURC", {std::string("content"), 0, 3, 3, 2,
                std::string(corrupt_chunk ? "62" : "6263")});
    }
    return true;
}
void voice_call_lock() { lock_depth++; }
void voice_call_unlock() { assert(lock_depth > 0); lock_depth--; }
call_state_t webrtc_get_call_state() { return fake_state; }
int xTaskCreate(void (*task)(void *), const char *, int, void *, int, TaskHandle_t *) {
    if (fail_task) return 0;
    task_count++;
    scheduled_task = task;
    return pdPASS;
}
TaskHandle_t xTaskGetCurrentTaskHandle() { return nullptr; }
void vTaskDelete(TaskHandle_t) {}
void vTaskDelay(unsigned) {}
SemaphoreHandle_t xSemaphoreCreateBinary() { return new unsigned(0); }
void vSemaphoreDelete(SemaphoreHandle_t h) { delete static_cast<unsigned *>(h); }
EventGroupHandle_t xEventGroupCreate() { return new unsigned(0); }
unsigned xEventGroupSetBits(EventGroupHandle_t h, unsigned bits) { return *h |= bits; }
unsigned xEventGroupWaitBits(EventGroupHandle_t h, unsigned mask, bool clear, bool all, unsigned wait) {
    unsigned bits = *h & mask;
    if (clear) *h &= ~mask;
    return bits;
}
void vEventGroupDelete(EventGroupHandle_t h) { delete h; }
const esp_partition_t *esp_ota_get_next_update_partition(const void *) { return &partition; }
const esp_partition_t *esp_ota_get_running_partition() { return &partition; }
int esp_ota_get_partition_description(const esp_partition_t *, esp_app_desc_t *) { return -1; }
int esp_ota_begin(const esp_partition_t *, unsigned, esp_ota_handle_t *h) { *h = 1; return ESP_OK; }
int esp_ota_write(esp_ota_handle_t, const void *data, size_t len) { written.append(static_cast<const char *>(data), len); return ESP_OK; }
int esp_ota_abort(esp_ota_handle_t) { abort_count++; return ESP_OK; }
int esp_ota_end(esp_ota_handle_t) { end_count++; return ESP_OK; }
int esp_ota_set_boot_partition(const esp_partition_t *) { boot_count++; return ESP_OK; }
int esp_task_wdt_add(TaskHandle_t) { return -1; }
int esp_task_wdt_delete(TaskHandle_t) { return -1; }
const char *esp_err_to_name(int) { return "fake"; }
void esp_restart() {
    assert(ota_is_in_progress()); // Calls remain blocked until the actual reboot.
    restart_count++;
    s_ota_in_progress = false; // Simulate reboot resetting static application state.
}
// Link Mbed TLS's real portable MD5 implementation without platform-specific helpers.
extern "C" void mbedtls_platform_zeroize(void *buffer, size_t len) {
    volatile unsigned char *bytes = static_cast<volatile unsigned char *>(buffer);
    while (len--) *bytes++ = 0;
}

static void reset_fixture() {
    assert(!ota_is_in_progress() && s_ota_context == nullptr && lock_depth == 0);
    scheduled_task = nullptr;
    task_count = abort_count = end_count = boot_count = restart_count = 0;
    fail_task = corrupt_chunk = false;
    fake_state = CALL_STATE_IDLE;
    written.clear();
}
static void run_download(const char *md5) {
    ota_start_upgrade("https://example.test/firmware.bin", md5);
    assert(ota_is_in_progress() && task_count == 1 && scheduled_task);
    scheduled_task(nullptr);
    assert(!ota_is_in_progress() && s_ota_context == nullptr && lock_depth == 0);
}

int main() {
    reset_fixture();
    run_download("900150983CD24FB0D6963F7D28E17F72"); // RFC 1321 MD5("abc"), uppercase accepted.
    assert(written == "abc" && end_count == 1 && boot_count == 1 && restart_count == 1 && abort_count == 0);

    reset_fixture();
    run_download("00000000000000000000000000000000");
    assert(written == "abc" && abort_count == 1 && end_count == 0 && boot_count == 0 && restart_count == 0);

    reset_fixture();
    run_download(nullptr); // Existing protocol permits absent MD5.
    assert(end_count == 1 && boot_count == 1);

    reset_fixture();
    corrupt_chunk = true;
    run_download("900150983cd24fb0d6963f7d28e17f72");
    assert(written == "a" && abort_count == 1 && boot_count == 0);

    reset_fixture();
    ota_start_upgrade(nullptr, nullptr);
    ota_start_upgrade("ftp://example.test/file", nullptr);
    ota_start_upgrade("https://example.test/\r\nAT", nullptr);
    ota_start_upgrade("https://example.test/file", "bad");
    ota_start_upgrade("https://example.test/file", "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz");
    assert(task_count == 0 && !ota_is_in_progress());

    reset_fixture();
    fake_state = CALL_STATE_CONNECTED;
    ota_start_upgrade("https://example.test/file", nullptr);
    assert(task_count == 0 && !ota_is_in_progress() && lock_depth == 0);

    reset_fixture();
    fail_task = true;
    ota_start_upgrade("https://example.test/file", nullptr);
    assert(!ota_is_in_progress());
    fail_task = false;
    run_download("");
    assert(boot_count == 1);

    reset_fixture();
    ota_start_upgrade("https://example.test/first.bin", nullptr);
    ota_start_upgrade("https://example.test/second.bin", nullptr);
    assert(task_count == 1 && std::string(s_ota_url) == "https://example.test/first.bin");
    scheduled_task(nullptr);
    assert(!ota_is_in_progress() && lock_depth == 0);
    puts("PASS: 8 OTA validation and cleanup scenarios");
}
