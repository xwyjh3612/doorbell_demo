#include "radar_presence.h"
#include "radar_frame_parser.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_console.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

// UART0: console GPIO43/44. UART1: ML307 GPIO17/18. UART2: radar RX6.
// Keep TAG/STATUS/HISTORY compatible with the existing read-only dashboard.
#define RADAR_UART UART_NUM_2
#define RADAR_RX GPIO_NUM_6
#define RADAR_UNUSED_TX GPIO_NUM_8
#define RADAR_BAUD 115200
#define RADAR_HISTORY_SIZE 512
static const char *TAG = "RADAR_GPIO5";
static SemaphoreHandle_t state_lock;
static QueueHandle_t commands, uart_events;
static radar_presence_snapshot_t state = {.presence = -1};
static radar_frame_parser_t parser;
static uint8_t history[RADAR_HISTORY_SIZE];
static size_t history_next, history_count;
typedef enum { RADAR_STATUS, RADAR_HISTORY } radar_command_t;

void radar_presence_get_snapshot(radar_presence_snapshot_t *snapshot)
{
    if (!snapshot) { return; }
    if (!state_lock) { *snapshot = state; return; }
    xSemaphoreTake(state_lock, portMAX_DELAY);
    *snapshot = state;
    xSemaphoreGive(state_lock);
}

static void on_frame(void *ctx, const uint8_t *frame, size_t size)
{
    (void)ctx;
    ++state.valid_frames;
    int presence = radar_frame_presence(frame, size);
    if (presence == -2) { return; }
    state.presence = presence;
    state.last_presence_ms = presence >= 0 ? esp_timer_get_time() / 1000 : 0;
}

static void show_status(void)
{
    radar_presence_snapshot_t s;
    radar_presence_get_snapshot(&s);
    ESP_LOGI(TAG, "STATUS rx=%d baud=%d bytes=%" PRIu64 " errors=%" PRIu32
             " header5359=%" PRIu64 " level=%d valid=%" PRIu64
             " invalid=%" PRIu32 " breaks=%" PRIu32 " presence=%d last_presence_ms=%" PRId64,
             RADAR_RX, RADAR_BAUD, s.received_bytes, s.uart_errors,
             s.header_candidates, gpio_get_level(RADAR_RX), s.valid_frames,
             s.invalid_frames, s.uart_breaks, s.presence, s.last_presence_ms);
}

static void show_history(void)
{
    // Called only by the UART reader task: snapshot bytes cannot interleave
    // with reception. No global/voice locks are held during console output.
    ESP_LOGI(TAG, "HISTORY rx=%d baud=%d saved=%u total=%" PRIu64 " last_ms=%" PRId64,
             RADAR_RX, RADAR_BAUD, (unsigned)history_count,
             state.received_bytes, state.last_rx_ms);
    uint8_t line[16];
    size_t first = (history_next + sizeof(history) - history_count) % sizeof(history);
    for (size_t offset = 0; offset < history_count;) {
        size_t count = history_count - offset;
        if (count > sizeof(line)) { count = sizeof(line); }
        for (size_t i = 0; i < count; ++i) {
            line[i] = history[(first + offset + i) % sizeof(history)];
        }
        ESP_LOG_BUFFER_HEX_LEVEL(TAG, line, count, ESP_LOG_INFO);
        offset += count;
    }
}

static int radar_cli(int argc, char **argv)
{
    radar_command_t command;
    if (argc == 1 || (argc == 2 && strcmp(argv[1], "status") == 0)) {
        command = RADAR_STATUS;
    } else if (argc == 2 && strcmp(argv[1], "history") == 0) {
        command = RADAR_HISTORY;
    } else {
        printf("radar status | radar history (read-only; fixed RX6/115200)\n");
        return 1;
    }
    if (!commands) { printf("Radar receiver unavailable; voice remains independent\n"); return 1; }
    if (xQueueSend(commands, &command, 0) != pdTRUE) {
        printf("Radar command queue busy; retry\n");
        return 1;
    }
    return 0;
}

esp_err_t radar_presence_register_console(void)
{
    const esp_console_cmd_t command = {
        .command = "radar", .help = "Read-only integrated R24D presence receiver",
        .func = radar_cli,
    };
    return esp_console_cmd_register(&command);
}

static void radar_reader(void *arg)
{
    (void)arg;
    uint8_t data[128], previous = 0;
    bool have_previous = false;
    int64_t summary_at = esp_timer_get_time();
    ESP_LOGI(TAG, "READY console=UART0 UART2 RX=GPIO6 baud=115200 8N1 TX=disabled firmware=voice-radar-1");
    for (;;) {
        radar_command_t command;
        // Bound work per iteration; repeated console queries cannot starve RX.
        if (xQueueReceive(commands, &command, 0) == pdTRUE) {
            if (command == RADAR_HISTORY) { show_history(); }
            show_status();
        }
        uart_event_t event;
        while (xQueueReceive(uart_events, &event, 0) == pdTRUE) {
            if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL ||
                event.type == UART_FRAME_ERR || event.type == UART_PARITY_ERR ||
                event.type == UART_BREAK) {
                xSemaphoreTake(state_lock, portMAX_DELAY);
                if (event.type == UART_BREAK) { ++state.uart_breaks; }
                else { ++state.uart_errors; }
                state.presence = -1;
                state.last_presence_ms = 0;
                radar_frame_parser_reset(&parser);
                xSemaphoreGive(state_lock);
                have_previous = false;
                if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL) {
                    uart_flush_input(RADAR_UART);
                    xQueueReset(uart_events);
                }
            }
        }
        int count = uart_read_bytes(RADAR_UART, data, sizeof(data), pdMS_TO_TICKS(50));
        int64_t now = esp_timer_get_time();
        if (count > 0) {
            xSemaphoreTake(state_lock, portMAX_DELAY);
            int old_presence = state.presence;
            state.received_bytes += count;
            state.last_rx_ms = now / 1000;
            for (int i = 0; i < count; ++i) {
                history[history_next] = data[i];
                history_next = (history_next + 1) % sizeof(history);
                if (history_count < sizeof(history)) { ++history_count; }
                if (have_previous && previous == 0x53 && data[i] == 0x59) { ++state.header_candidates; }
                previous = data[i];
                have_previous = true;
            }
            radar_frame_parser_feed(&parser, data, count, on_frame, NULL);
            state.invalid_frames = parser.invalid_frames;
            int presence = state.presence;
            xSemaphoreGive(state_lock);
            if (presence != old_presence) {
                ESP_LOGI(TAG, "PRESENCE %s (last validated report; no call action)",
                         presence < 0 ? "unknown" : presence ? "occupied" : "unoccupied");
            }
        } else if (count < 0) {
            xSemaphoreTake(state_lock, portMAX_DELAY);
            ++state.uart_errors;
            xSemaphoreGive(state_lock);
        }
        if (now - summary_at >= 3000000) {
            show_status();
            summary_at = now;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

esp_err_t radar_presence_start(void)
{
#if !CONFIG_IDF_TARGET_ESP32S3
    return ESP_ERR_NOT_SUPPORTED;
#else
    if (state.enabled) { return ESP_OK; }
    if (uart_is_driver_installed(RADAR_UART)) { return ESP_ERR_INVALID_STATE; }
    state_lock = xSemaphoreCreateMutex();
    commands = xQueueCreate(4, sizeof(radar_command_t));
    esp_err_t ret = ESP_ERR_NO_MEM;
    bool installed = false;
    if (!state_lock || !commands) { goto fail; }
    ret = gpio_reset_pin(RADAR_UNUSED_TX);
    if (ret != ESP_OK) { goto fail; }
    ret = gpio_set_direction(RADAR_UNUSED_TX, GPIO_MODE_INPUT);
    if (ret != ESP_OK) { goto fail; }
    ret = gpio_set_pull_mode(RADAR_UNUSED_TX, GPIO_FLOATING);
    if (ret != ESP_OK) { goto fail; }
    const uart_config_t config = {
        .baud_rate = RADAR_BAUD, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
    };
    ret = uart_driver_install(RADAR_UART, 4096, 0, 16, &uart_events, 0);
    if (ret != ESP_OK) { goto fail; }
    installed = true;
    ret = uart_param_config(RADAR_UART, &config);
    if (ret != ESP_OK) { goto fail; }
    ret = gpio_reset_pin(RADAR_RX);
    if (ret != ESP_OK) { goto fail; }
    ret = gpio_set_direction(RADAR_RX, GPIO_MODE_INPUT);
    if (ret != ESP_OK) { goto fail; }
    ret = gpio_set_pull_mode(RADAR_RX, GPIO_FLOATING);
    if (ret != ESP_OK) { goto fail; }
    ret = uart_set_pin(RADAR_UART, UART_PIN_NO_CHANGE, RADAR_RX,
                       UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (ret != ESP_OK) { goto fail; }
    state.enabled = true;
    if (xTaskCreate(radar_reader, "radar_rx", 4096, NULL, 2, NULL) == pdPASS) { return ESP_OK; }
    state.enabled = false;
    ret = ESP_ERR_NO_MEM;
fail:
    if (installed) { uart_driver_delete(RADAR_UART); }
    uart_events = NULL;
    if (commands) { vQueueDelete(commands); commands = NULL; }
    if (state_lock) { vSemaphoreDelete(state_lock); state_lock = NULL; }
    return ret;
#endif
}
