#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_console.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

// Module RX -> ESP32 GPIO8 (TX); module TX -> ESP32 GPIO5 (RX).
// UART0 is the console and UART1 belongs to the doorbell's 4G modem.
#define RADAR_UART UART_NUM_2
#define RADAR_TX_GPIO 8
#define RADAR_RX_GPIO 5
#define RADAR_DEFAULT_BAUD 9600
#define RAW_BYTES_PER_SECOND 512

static const char *TAG = "RADAR";
static QueueHandle_t commands;
static QueueHandle_t uart_events;

typedef enum { CMD_STATUS, CMD_BAUD, CMD_RAW } command_kind_t;
typedef struct {
    command_kind_t kind;
    int value;
} radar_command_t;

static bool supported_baud(long baud)
{
    return baud == 9600 || baud == 19200 || baud == 38400 ||
           baud == 57600 || baud == 115200 || baud == 256000;
}

static int radar_cli(int argc, char **argv)
{
    radar_command_t command = { .kind = CMD_STATUS };
    if (argc == 1 || (argc == 2 && strcmp(argv[1], "status") == 0)) {
        command.kind = CMD_STATUS;
    } else if (argc == 3 && strcmp(argv[1], "baud") == 0) {
        char *end = NULL;
        errno = 0;
        long baud = strtol(argv[2], &end, 10);
        if (errno || end == argv[2] || *end || !supported_baud(baud)) {
            printf("Supported radar baud: 9600 19200 38400 57600 115200 256000\n");
            return 1;
        }
        command.kind = CMD_BAUD;
        command.value = (int)baud;
    } else if (argc == 3 && strcmp(argv[1], "raw") == 0 &&
               (strcmp(argv[2], "on") == 0 || strcmp(argv[2], "off") == 0)) {
        command.kind = CMD_RAW;
        command.value = strcmp(argv[2], "on") == 0;
    } else {
        printf("radar status | radar baud <rate> | radar raw on/off\n");
        return 1;
    }
    if (xQueueSend(commands, &command, pdMS_TO_TICKS(100)) != pdTRUE) {
        printf("Radar command queue full; retry\n");
        return 1;
    }
    return 0;
}

static void radar_reader(void *argument)
{
    int baud = RADAR_DEFAULT_BAUD;
    bool raw_enabled = true;
    uint64_t total_bytes = 0;
    uint32_t errors = 0;
    int64_t last_summary = esp_timer_get_time();
    int64_t raw_window = last_summary;
    size_t raw_budget = RAW_BYTES_PER_SECOND;
    uint8_t data[128];

    ESP_LOGI(TAG, "READY UART2 TX=GPIO%d RX=GPIO%d baud=%d 8N1 (receive only)",
             RADAR_TX_GPIO, RADAR_RX_GPIO, baud);
    ESP_LOGI(TAG, "Module RX -> GPIO8; module TX -> GPIO5; 5V power; common GND");

    for (;;) {
        radar_command_t command;
        while (xQueueReceive(commands, &command, 0) == pdTRUE) {
            if (command.kind == CMD_BAUD) {
                // Only this task owns the UART, including baud changes and reads.
                esp_err_t result = uart_set_baudrate(RADAR_UART, command.value);
                if (result != ESP_OK) {
                    ESP_LOGE(TAG, "Baud change failed: %s", esp_err_to_name(result));
                    continue;
                }
                ESP_ERROR_CHECK(uart_flush_input(RADAR_UART));
                xQueueReset(uart_events);
                baud = command.value;
                total_bytes = 0;
                errors = 0;
                last_summary = raw_window = esp_timer_get_time();
                raw_budget = RAW_BYTES_PER_SECOND;
                ESP_LOGI(TAG, "Baud now %d; counters reset; no command sent to module", baud);
            } else if (command.kind == CMD_RAW) {
                raw_enabled = command.value != 0;
                ESP_LOGI(TAG, "Raw output %s", raw_enabled ? "on" : "off");
            } else {
                ESP_LOGI(TAG, "STATUS baud=%d bytes=%" PRIu64 " errors=%" PRIu32 " RX_level=%d raw=%s",
                         baud, total_bytes, errors, gpio_get_level(RADAR_RX_GPIO),
                         raw_enabled ? "on" : "off");
            }
        }

        uart_event_t event;
        while (xQueueReceive(uart_events, &event, 0) == pdTRUE) {
            if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL ||
                event.type == UART_FRAME_ERR || event.type == UART_PARITY_ERR) {
                ++errors;
                ESP_LOGW(TAG, "UART error type=%d; check baud, wiring and voltage", event.type);
                if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL) {
                    ESP_ERROR_CHECK(uart_flush_input(RADAR_UART));
                    xQueueReset(uart_events);
                }
            }
        }

        int count = uart_read_bytes(RADAR_UART, data, sizeof(data), pdMS_TO_TICKS(50));
        int64_t now = esp_timer_get_time();
        if (now - raw_window >= 1000000) {
            raw_window = now;
            raw_budget = RAW_BYTES_PER_SECOND;
        }
        if (count > 0) {
            total_bytes += count;
            size_t shown = (size_t)count < raw_budget ? (size_t)count : raw_budget;
            if (raw_enabled && shown) {
                // These are UART read chunks, not decoded protocol frames.
                ESP_LOGI(TAG, "RX baud=%d count=%d (hex, UART chunk)", baud, count);
                ESP_LOG_BUFFER_HEX_LEVEL(TAG, data, shown, ESP_LOG_INFO);
                raw_budget -= shown;
                if (shown < (size_t)count) {
                    ESP_LOGI(TAG, "Raw log capped at %d bytes/s; counters include all received bytes",
                             RAW_BYTES_PER_SECOND);
                }
            }
        } else if (count < 0) {
            ++errors;
            ESP_LOGE(TAG, "UART read failed");
        }
        if (now - last_summary >= 5000000) {
            ESP_LOGI(TAG, "STATUS baud=%d bytes=%" PRIu64 " errors=%" PRIu32 " RX_level=%d",
                     baud, total_bytes, errors, gpio_get_level(RADAR_RX_GPIO));
            if (!total_bytes) {
                ESP_LOGW(TAG, "No RX data yet: check module TX -> GPIO5, power, GND, then radar baud");
            }
            last_summary = now;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

void app_main(void)
{
    commands = xQueueCreate(8, sizeof(radar_command_t));
    ESP_ERROR_CHECK(commands ? ESP_OK : ESP_ERR_NO_MEM);
    const uart_config_t uart_config = {
        .baud_rate = RADAR_DEFAULT_BAUD,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(RADAR_UART, 4096, 0, 16, &uart_events, 0));
    ESP_ERROR_CHECK(uart_param_config(RADAR_UART, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(RADAR_UART, RADAR_TX_GPIO, RADAR_RX_GPIO,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(xTaskCreate(radar_reader, "radar_reader", 4096, NULL, 5, NULL) == pdPASS
                    ? ESP_OK : ESP_ERR_NO_MEM);

    esp_console_repl_t *repl = NULL;
    esp_console_repl_config_t repl_config = ESP_CONSOLE_REPL_CONFIG_DEFAULT();
    repl_config.prompt = "radar>";
    const esp_console_dev_uart_config_t console_config = ESP_CONSOLE_DEV_UART_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_console_new_repl_uart(&console_config, &repl_config, &repl));
    const esp_console_cmd_t radar_command = {
        .command = "radar",
        .help = "radar status | radar baud <rate> | radar raw on/off (read only)",
        .func = radar_cli,
    };
    ESP_ERROR_CHECK(esp_console_cmd_register(&radar_command));
    ESP_ERROR_CHECK(esp_console_start_repl(repl));
}
