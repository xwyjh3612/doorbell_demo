#include "status_indicator.h"
#include "status_indicator_logic.h"
#include "network_4g.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {
constexpr gpio_num_t STATUS_GPIO = GPIO_NUM_39;
TaskHandle_t indicator_task;
rmt_channel_handle_t channel;
rmt_encoder_handle_t encoder;

esp_err_t send_color(status_indicator_rgb rgb)
{
    // WS2812B-2020-V6: GRB, MSB first. At 20MHz, 0=350ns/950ns,
    // 1=700ns/600ns; both total 1.3us, with margin to pulse limits.
    // Reset stays low for 300.05us.
    // Hardware RMT generates the waveform without disabling interrupts or
    // busy waiting in the audio/AT tasks.
    rmt_symbol_word_t symbols[25]{};
    const uint8_t bytes[] = {rgb.green, rgb.red, rgb.blue};
    unsigned n = 0;
    for (uint8_t byte : bytes) {
        for (int bit = 7; bit >= 0; --bit) {
            const bool one = byte & (1U << bit);
            symbols[n].level0 = 1;
            symbols[n].duration0 = one ? 14 : 7;
            symbols[n].level1 = 0;
            symbols[n++].duration1 = one ? 12 : 19;
        }
    }
    symbols[24].duration0 = 6000;
    symbols[24].duration1 = 1;
    rmt_transmit_config_t tx{};
    esp_err_t ret = rmt_transmit(channel, encoder, symbols, sizeof(symbols), &tx);
    if (ret != ESP_OK) return ret;
    // Keep stack payload alive until the hardware transmission finishes.
    // This dedicated priority-1 task never blocks a media or modem task.
    return rmt_tx_wait_all_done(channel, -1);
}

void indicate(void *)
{
    status_indicator_mode mode = status_indicator_mode::offline;
    int64_t mode_started = esp_timer_get_time() / 1000;
    int previous = -1;
    for (;;) {
        // GetMqttInstance reads a published atomic pointer. The existing ML307
        // IsConnected reads its local atomic URC state; no AT/MQTT request.
        Mqtt *mqtt = Network4g::GetMqttInstance();
        const auto selected = status_indicator_select(mqtt && mqtt->IsConnected(),
                                                       webrtc_get_call_state());
        const int64_t now = esp_timer_get_time() / 1000;
        if (selected != mode) { mode = selected; mode_started = now; }
        const bool lit = status_indicator_on(mode, now - mode_started);
        const int frame = lit ? 1 + static_cast<int>(mode) : 0;
        if (frame != previous && send_color(lit ? status_indicator_color(mode)
                                               : status_indicator_rgb{0, 0, 0}) == ESP_OK)
            previous = frame;
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
}

extern "C" esp_err_t status_indicator_start(void)
{
    if (indicator_task) return ESP_OK;
    rmt_tx_channel_config_t cfg{};
    cfg.gpio_num = STATUS_GPIO;
    cfg.clk_src = RMT_CLK_SRC_DEFAULT;
    cfg.resolution_hz = 20000000;
    cfg.mem_block_symbols = 48;
    cfg.trans_queue_depth = 1;
    esp_err_t ret = rmt_new_tx_channel(&cfg, &channel);
    if (ret != ESP_OK) return ret;
    rmt_copy_encoder_config_t enc{};
    ret = rmt_new_copy_encoder(&enc, &encoder);
    if (ret == ESP_OK) ret = rmt_enable(channel);
    if (ret == ESP_OK) ret = send_color({0, 0, 0});
    if (ret == ESP_OK && xTaskCreate(indicate, "status_led", 3072, nullptr, 1, &indicator_task) != pdPASS)
        ret = ESP_ERR_NO_MEM;
    if (ret == ESP_OK) return ESP_OK;
    rmt_disable(channel);
    if (encoder) { rmt_del_encoder(encoder); encoder = nullptr; }
    rmt_del_channel(channel); channel = nullptr;
    return ret;
}
