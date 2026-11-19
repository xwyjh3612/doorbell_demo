#include "firmware_stubs.h"
// Generated from the entire production file with framework includes replaced by host stubs.
#include "firmware_under_test.inc"

typedef struct {
    unsigned capacity, size, head, count;
    unsigned char items[24][128];
} FakeQueue;
static TickType_t fake_now;
static bool fake_ota;
static int ring_count, disable_count, close_count, timeout_count;
static int tone_count, active_tone = -1;
static event_handler_t fake_event_handler;
static app_config_t config = {.call_timeout = 120};

TickType_t xTaskGetTickCount(void) { return fake_now; }
int xTaskCreate(void (*task)(void *), const char *name, int stack, void *arg, int priority, TaskHandle_t *handle) { return pdPASS; }
QueueHandle_t xQueueCreate(unsigned capacity, size_t size) {
    assert(capacity <= 24 && size <= 128);
    FakeQueue *q = calloc(1, sizeof(*q));
    q->capacity = capacity;
    q->size = (unsigned)size;
    return q;
}
int xQueueSend(QueueHandle_t handle, const void *item, TickType_t wait) {
    FakeQueue *q = handle;
    if (q->count == q->capacity) return 0;
    memcpy(q->items[(q->head + q->count++) % q->capacity], item, q->size);
    return pdPASS;
}
int xQueueReceive(QueueHandle_t handle, void *item, TickType_t wait) {
    FakeQueue *q = handle;
    if (!q->count) return 0;
    memcpy(item, q->items[q->head], q->size);
    q->head = (q->head + 1) % q->capacity;
    q->count--;
    return pdPASS;
}
void vQueueDelete(QueueHandle_t q) { free(q); }
SemaphoreHandle_t xSemaphoreCreateRecursiveMutex(void) { return (void *)1; }
int xSemaphoreTakeRecursive(SemaphoreHandle_t m, TickType_t wait) { return pdPASS; }
int xSemaphoreGiveRecursive(SemaphoreHandle_t m) { return pdPASS; }
void vSemaphoreDelete(SemaphoreHandle_t m) {}
int gpio_config(const gpio_config_t *c) { return 0; }
int gpio_get_level(int p) { return 0; }
void media_lib_thread_sleep(int ms) {}
int media_lib_thread_create_from_scheduler(media_lib_thread_handle_t *h, const char *name, void (*task)(void *), void *arg) { return 0; }
int esp_webrtc_send_custom_data(esp_webrtc_handle_t h, int via, uint8_t *data, size_t size) { return 0; }
int esp_webrtc_enable_peer_connection(esp_webrtc_handle_t h, bool enable) {
    assert(h);
    if (!enable) {
        disable_count++;
        if (fake_event_handler) {
            esp_webrtc_event_t event = {.type = ESP_WEBRTC_EVENT_DISCONNECTED};
            fake_event_handler(&event, NULL);
        }
    }
    return 0;
}
int esp_webrtc_open(const esp_webrtc_cfg_t *cfg, esp_webrtc_handle_t *h) { *h = (void *)1; return 0; }
int esp_webrtc_close(esp_webrtc_handle_t h) { close_count++; return 0; }
int esp_webrtc_start(esp_webrtc_handle_t h) { return 0; }
int esp_webrtc_query(esp_webrtc_handle_t h) { return 0; }
int esp_webrtc_set_media_provider(esp_webrtc_handle_t h, esp_webrtc_media_provider_t *p) { return 0; }
int esp_webrtc_set_event_handler(esp_webrtc_handle_t h, event_handler_t cb, void *ctx) { fake_event_handler = cb; return 0; }
void *esp_peer_get_default_impl(void) { return NULL; }
int media_sys_get_provider(esp_webrtc_media_provider_t *p) { return 0; }
int stop_music(void) { active_tone = -1; return 0; }
int play_tone(door_bell_tone_type_t tone) { tone_count++; active_tone = tone; return 0; }
app_config_t *app_config_get(void) { return &config; }
bool ota_is_in_progress(void) { return fake_ota; }
void mqtt_sig_set_event_handler(mqtt_sig_event_cb_t cb, void *ctx) {}
void mqtt_sig_set_webrtc_handle(void *h) {}
void mqtt_sig_send_ring(const char *target) { ring_count++; }
void mqtt_sig_send_timeout(const char *target) { timeout_count++; }
void mqtt_sig_answer_call(void) {}
void mqtt_sig_reject_call(void) {}
void mqtt_sig_close_call(void) {}
const esp_peer_signaling_impl_t *esp_signaling_get_mqtt_impl(void) { return NULL; }

static void pump(void) {
    call_action_t action;
    unsigned iterations = 0;
    while (xQueueReceive(call_actions, &action, 0) == pdPASS) {
        assert(++iterations < 100);
        process_action(&action);
    }
    process_call_deadlines();
}
static void peer_event(esp_webrtc_event_type_t type) {
    esp_webrtc_event_t event = {.type = type};
    assert(webrtc_event_handler(&event, NULL) == 0);
    pump();
}
static void reset_fixture(void) {
    fake_ota = false;
    config.call_timeout = 120;
    fake_now = 0;
    stop_webrtc();
    assert(start_webrtc("mqtt") == 0);
    pump();
    ring_count = disable_count = close_count = timeout_count = 0;
    tone_count = 0;
    active_tone = -1;
}
static void connected_call(void) {
    assert(voice_call_offer("remote_a") == 0);
    pump();
    assert(webrtc_get_call_state() == CALL_STATE_OUTGOING);
    peer_event(ESP_WEBRTC_EVENT_CONNECTED);
    assert(webrtc_get_call_state() == CALL_STATE_CONNECTED);
}
static void advance(TickType_t ms) { fake_now += ms; pump(); }

static void test_close_then_redial(void) {
    reset_fixture();
    connected_call();
    send_cmd("close");
    // Queue the new call before the old connection emits its final event.
    assert(voice_call_offer("remote_b") == 0);
    pump();
    assert(close_count == 0 && webrtc != NULL);
    assert(ring_count == 2 && webrtc_get_call_state() == CALL_STATE_OUTGOING);
    assert(strcmp(webrtc_get_peer_id(), "remote_b") == 0);
}
static void test_three_retries_after_disconnect(void) {
    reset_fixture();
    connected_call();
    esp_webrtc_event_t event = {.type = ESP_WEBRTC_EVENT_DISCONNECTED};
    webrtc_event_handler(&event, NULL);
    assert(disable_count == 0); // Framework callbacks must not close their own task.
    pump();
    for (int attempt = 1; attempt <= 3; attempt++) {
        assert(webrtc_get_call_state() == CALL_STATE_RECONNECTING);
        advance(1500);
        assert(ring_count == attempt + 1);
        assert(strcmp(g_call_ctx.last_remote_id, "remote_a") == 0);
        peer_event(ESP_WEBRTC_EVENT_CONNECT_FAILED);
    }
    assert(webrtc_get_call_state() == CALL_STATE_IDLE);
    advance(60000);
    assert(ring_count == 4);
}
static void test_retry_timeout_and_cancel(void) {
    reset_fixture();
    config.call_timeout = 7;
    connected_call();
    peer_event(ESP_WEBRTC_EVENT_DISCONNECTED);
    advance(1500);
    advance(6999);
    assert(timeout_count == 0);
    advance(1);
    assert(timeout_count == 1 && webrtc_get_call_state() == CALL_STATE_RECONNECTING);
    send_cmd("close");
    pump();
    advance(60000);
    assert(ring_count == 2 && webrtc_get_call_state() == CALL_STATE_IDLE);
}
static void test_answer_does_not_cancel_connection_timeout(void) {
    reset_fixture();
    config.call_timeout = 3;
    voice_call_offer("remote_a");
    pump();
    on_mqtt_signaling_event(MQTT_SIG_EVENT_REMOTE_ANSWER, "", NULL);
    pump();
    assert(webrtc_get_call_state() == CALL_STATE_OUTGOING_CONNECTING);
    advance(3000);
    assert(timeout_count == 1 && webrtc_get_call_state() == CALL_STATE_IDLE);
    assert(ring_count == 1); // Initial failures are not redialed.
}
static void test_remote_bye_stops_redial(void) {
    reset_fixture();
    connected_call();
    on_mqtt_signaling_event(MQTT_SIG_EVENT_REMOTE_CLOSE, "", NULL);
    pump();
    advance(60000);
    assert(ring_count == 1 && webrtc_get_call_state() == CALL_STATE_IDLE);
}
static void test_busy_offer_cannot_replace_peer(void) {
    reset_fixture();
    connected_call();
    assert(voice_call_offer("remote_b") == 0);
    pump();
    assert(strcmp(webrtc_get_peer_id(), "remote_a") == 0 && ring_count == 1);
}
static void test_restart_drops_old_commands(void) {
    reset_fixture();
    voice_call_offer("old_remote");
    stop_webrtc();
    start_webrtc("mqtt");
    pump();
    assert(ring_count == 0 && webrtc_get_call_state() == CALL_STATE_IDLE);
}
static void test_tick_wrap_and_ota_guard(void) {
    reset_fixture();
    config.call_timeout = 2;
    fake_now = UINT32_MAX - 500;
    voice_call_offer("remote_a");
    pump();
    advance(1999);
    assert(timeout_count == 0);
    advance(1);
    assert(timeout_count == 1);
    fake_ota = true;
    voice_call_offer("remote_b");
    pump();
    assert(ring_count == 1 && webrtc_get_call_state() == CALL_STATE_IDLE);
}

static void test_call_tones_and_network_prompt(void) {
    reset_fixture();
    assert(tone_count == 0); // Starting signaling alone must not announce online.
    on_mqtt_signaling_event(MQTT_SIG_EVENT_NETWORK_READY, "", NULL);
    pump();
    assert(active_tone == DOOR_BELL_TONE_NETWORK_SUCCESS && tone_count == 1);
    send_cmd("ring");
    pump();
    assert(active_tone == DOOR_BELL_TONE_OUTGOING && tone_count == 2);
    on_mqtt_signaling_event(MQTT_SIG_EVENT_NETWORK_READY, "", NULL);
    pump();
    assert(active_tone == DOOR_BELL_TONE_OUTGOING && tone_count == 2);
    peer_event(ESP_WEBRTC_EVENT_CONNECTED);
    assert(active_tone == -1);
    on_mqtt_signaling_event(MQTT_SIG_EVENT_NETWORK_READY, "", NULL);
    pump();
    assert(active_tone == -1 && tone_count == 2);
    send_cmd("close");
    pump();
    on_mqtt_signaling_event(MQTT_SIG_EVENT_REMOTE_OFFER, "remote_a", NULL);
    pump();
    assert(active_tone == DOOR_BELL_TONE_INCOMING && tone_count == 3);
    send_cmd("answer");
    pump();
    assert(active_tone == -1);
    send_cmd("close");
    pump();
    fake_ota = true;
    on_mqtt_signaling_event(MQTT_SIG_EVENT_NETWORK_READY, "", NULL);
    pump();
    assert(active_tone == -1 && tone_count == 3);
}

int main(void) {
    test_close_then_redial();
    test_three_retries_after_disconnect();
    test_retry_timeout_and_cancel();
    test_answer_does_not_cancel_connection_timeout();
    test_remote_bye_stops_redial();
    test_busy_offer_cannot_replace_peer();
    test_restart_drops_old_commands();
    test_tick_wrap_and_ota_guard();
    test_call_tones_and_network_prompt();
    puts("PASS: 9 call lifecycle scenarios, including distinct call tones and guarded network prompt");
    return 0;
}
