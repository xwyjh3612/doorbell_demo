#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_check.h"
#include "esp_console.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

// UART0 console uses GPIO43/44 via the board's CH343 (COM13).
// Radar TX connects to independent GPIO5 / UART2 RX.
// GPIO8 is an input only; radar RX can remain attached but is not driven.
// Never attach radar data wires to the UART0 console pins in this app.
// No UART TX output or radar commands are used by this diagnostic app.
#define RADAR_UART UART_NUM_2
#define DEFAULT_RX_GPIO 5
#define DEFAULT_BAUD 115200
#define RAW_LIMIT 512
#define HISTORY_SIZE 512

static const char *TAG = "RADAR_GPIO5";
static QueueHandle_t commands;
static QueueHandle_t uart_events;

typedef enum { STATUS, BAUD, RX_PIN, RAW, CLEAR, HISTORY } command_kind_t;
typedef struct { command_kind_t kind; int value; } command_t;

static bool parse_number(const char *text, int *number)
{
    char *end = NULL;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno || end == text || *end || value < 0 || value > 1000000) {
        return false;
    }
    *number = (int)value;
    return true;
}

static bool valid_baud(int value)
{
    return value == 9600 || value == 19200 || value == 38400 ||
           value == 57600 || value == 115200 || value == 256000;
}

static int radar_cli(int argc, char **argv)
{
    command_t cmd = { .kind = STATUS };
    if (argc == 1 || (argc == 2 && strcmp(argv[1], "status") == 0)) {
        cmd.kind = STATUS;
    } else if (argc == 2 && strcmp(argv[1], "clear") == 0) {
        cmd.kind = CLEAR;
    } else if (argc == 2 && strcmp(argv[1], "history") == 0) {
        cmd.kind = HISTORY;
    } else if (argc == 3 && strcmp(argv[1], "baud") == 0 &&
               parse_number(argv[2], &cmd.value) && valid_baud(cmd.value)) {
        cmd.kind = BAUD;
    } else if (argc == 3 && strcmp(argv[1], "rx") == 0 &&
               parse_number(argv[2], &cmd.value) &&
               (cmd.value == 5 || cmd.value == 6 || cmd.value == 8)) {
        cmd.kind = RX_PIN;
    } else if (argc == 3 && strcmp(argv[1], "raw") == 0 &&
               (strcmp(argv[2], "on") == 0 || strcmp(argv[2], "off") == 0)) {
        cmd.kind = RAW;
        cmd.value = strcmp(argv[2], "on") == 0;
    } else {
        printf("radar status | clear | baud <9600/19200/38400/57600/115200/256000>\n"
               "radar rx <5/6/8> | radar raw on/off | radar history\n"
               "Radar TX -> selected GPIO; GPIO43/44 are the UART0 console.\n");
        return 1;
    }
    if (xQueueSend(commands, &cmd, pdMS_TO_TICKS(100)) != pdTRUE) {
        printf("Command queue full; retry\n");
        return 1;
    }
    return 0;
}

static esp_err_t configure_rx(int pin)
{
    // Only independent GPIO5/6/8 are accepted; leave UART0 console pins alone.
    ESP_RETURN_ON_ERROR(gpio_reset_pin(pin), TAG, "reset RX GPIO");
    ESP_RETURN_ON_ERROR(gpio_set_direction(pin, GPIO_MODE_INPUT), TAG, "RX input");
    // Keep the input unbiased: a floating reading does not prove radar power.
    ESP_RETURN_ON_ERROR(gpio_set_pull_mode(pin, GPIO_FLOATING), TAG, "RX pull");
    return uart_set_pin(RADAR_UART, UART_PIN_NO_CHANGE, pin,
                        UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
}

static void radar_reader(void *arg)
{
    (void)arg;
    int pin = DEFAULT_RX_GPIO, baud = DEFAULT_BAUD;
    bool raw = true, have_previous = false;
    uint8_t previous = 0, data[128];
    uint8_t history[HISTORY_SIZE];
    size_t history_next = 0, history_count = 0;
    int64_t history_last_us = 0;
    uint64_t bytes = 0, header_candidates = 0;
    uint32_t errors = 0;
    int64_t summary_at = esp_timer_get_time(), window_at = summary_at;
    size_t raw_left = RAW_LIMIT;
    ESP_LOGI(TAG, "READY console=UART0 UART2 RX=GPIO%d baud=%d 8N1 TX=disabled",
             pin, baud);
    ESP_LOGI(TAG, "Radar TX -> GPIO5; GPIO8 is input only; radar RX is not driven.");

    for (;;) {
        command_t cmd;
        while (xQueueReceive(commands, &cmd, 0) == pdTRUE) {
            bool clear = false;
            esp_err_t ret = ESP_OK;
            if (cmd.kind == RX_PIN) {
                ret = configure_rx(cmd.value);
                if (ret == ESP_OK) {
                    if (pin != cmd.value) {
                        gpio_reset_pin(pin);
                        gpio_set_direction(pin, GPIO_MODE_INPUT);
                    }
                    pin = cmd.value;
                    clear = true;
                }
            } else if (cmd.kind == BAUD) {
                ret = uart_set_baudrate(RADAR_UART, cmd.value);
                if (ret == ESP_OK) { baud = cmd.value; clear = true; }
            } else if (cmd.kind == RAW) {
                raw = cmd.value != 0;
            } else if (cmd.kind == CLEAR) {
                clear = true;
            } else if (cmd.kind == HISTORY) {
                // Saved RX bytes only; no GPIO outputs or radar queries.
                ESP_LOGI(TAG, "HISTORY rx=%d baud=%d saved=%u total=%" PRIu64
                         " last_ms=%" PRId64 " (oldest to newest; UART stream)",
                         pin, baud, (unsigned)history_count, bytes,
                         history_last_us / 1000);
                size_t first = (history_next + HISTORY_SIZE - history_count) % HISTORY_SIZE;
                size_t remaining = history_count;
                while (remaining) {
                    size_t shown = remaining < sizeof(data) ? remaining : sizeof(data);
                    for (size_t i = 0; i < shown; ++i) {
                        data[i] = history[(first + i) % HISTORY_SIZE];
                    }
                    ESP_LOG_BUFFER_HEX_LEVEL(TAG, data, shown, ESP_LOG_INFO);
                    first = (first + shown) % HISTORY_SIZE;
                    remaining -= shown;
                }
            }
            if (ret != ESP_OK) {
                ESP_LOGE(TAG, "Configuration failed: %s", esp_err_to_name(ret));
                continue;
            }
            if (clear) {
                ESP_ERROR_CHECK(uart_flush_input(RADAR_UART));
                xQueueReset(uart_events);
                bytes = header_candidates = errors = 0;
                have_previous = false;
                history_next = history_count = 0;
                history_last_us = 0;
                summary_at = window_at = esp_timer_get_time();
                raw_left = RAW_LIMIT;
            }
            ESP_LOGI(TAG, "STATUS rx=%d baud=%d bytes=%" PRIu64
                     " errors=%" PRIu32 " header5359=%" PRIu64 " level=%d raw=%s",
                     pin, baud, bytes, errors, header_candidates,
                     gpio_get_level(pin), raw ? "on" : "off");
        }
        uart_event_t event;
        while (xQueueReceive(uart_events, &event, 0) == pdTRUE) {
            if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL ||
                event.type == UART_FRAME_ERR || event.type == UART_PARITY_ERR) {
                ++errors;
                ESP_LOGW(TAG, "UART error type=%d", event.type);
                if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL) {
                    ESP_ERROR_CHECK(uart_flush_input(RADAR_UART));
                    xQueueReset(uart_events);
                    have_previous = false;
                }
            } else if (event.type == UART_BREAK) {
                ESP_LOGW(TAG, "UART BREAK: RX held low; check wiring/power");
            }
        }
        int count = uart_read_bytes(RADAR_UART, data, sizeof(data), pdMS_TO_TICKS(50));
        int64_t now = esp_timer_get_time();
        if (now - window_at >= 1000000) {
            window_at = now;
            raw_left = RAW_LIMIT;
        }
        if (count > 0) {
            bytes += count;
            for (int i = 0; i < count; ++i) {
                history[history_next] = data[i];
                history_next = (history_next + 1) % HISTORY_SIZE;
                if (history_count < HISTORY_SIZE) {
                    ++history_count;
                }
                if (have_previous && previous == 0x53 && data[i] == 0x59) {
                    ++header_candidates;
                }
                previous = data[i];
                have_previous = true;
            }
            history_last_us = now;
            size_t shown = (size_t)count < raw_left ? (size_t)count : raw_left;
            if (raw && shown) {
                ESP_LOGI(TAG, "RAW rx=%d baud=%d received=%d shown=%u (UART chunk)",
                         pin, baud, count, (unsigned)shown);
                ESP_LOG_BUFFER_HEX_LEVEL(TAG, data, shown, ESP_LOG_INFO);
                raw_left -= shown;
            }
        } else if (count < 0) {
            ++errors;
        }
        if (now - summary_at >= 3000000) {
            ESP_LOGI(TAG, "STATUS rx=%d baud=%d bytes=%" PRIu64
                     " errors=%" PRIu32 " header5359=%" PRIu64 " level=%d",
                     pin, baud, bytes, errors, header_candidates, gpio_get_level(pin));
            summary_at = now;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

void app_main(void)
{
    // Keep the radar's RX input undriven, even if attached to GPIO8.
    ESP_ERROR_CHECK(gpio_reset_pin(GPIO_NUM_8));
    ESP_ERROR_CHECK(gpio_set_direction(GPIO_NUM_8, GPIO_MODE_INPUT));
    ESP_ERROR_CHECK(gpio_set_pull_mode(GPIO_NUM_8, GPIO_FLOATING));
    commands = xQueueCreate(8, sizeof(command_t));
    ESP_ERROR_CHECK(commands ? ESP_OK : ESP_ERR_NO_MEM);
    uart_config_t cfg = {
        .baud_rate = DEFAULT_BAUD, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(RADAR_UART, 4096, 0, 16, &uart_events, 0));
    ESP_ERROR_CHECK(uart_param_config(RADAR_UART, &cfg));
    ESP_ERROR_CHECK(configure_rx(DEFAULT_RX_GPIO));
    esp_console_repl_t *repl = NULL;
    esp_console_repl_config_t repl_cfg = ESP_CONSOLE_REPL_CONFIG_DEFAULT();
    repl_cfg.prompt = "radar-gpio5>";
    esp_console_dev_uart_config_t console_cfg = ESP_CONSOLE_DEV_UART_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_console_new_repl_uart(&console_cfg, &repl_cfg, &repl));
    esp_console_cmd_t cmd = {
        .command = "radar", .help = "Read-only radar pin/baud diagnostics",
        .func = radar_cli,
    };
    ESP_ERROR_CHECK(esp_console_cmd_register(&cmd));
    ESP_ERROR_CHECK(xTaskCreate(radar_reader, "radar_reader", 4096, NULL, 5, NULL) == pdPASS
                    ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_ERROR_CHECK(esp_console_start_repl(repl));
}
