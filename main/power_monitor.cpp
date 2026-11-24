#include "power_monitor.h"
#include "power_monitor_logic.h"
#include "app_config.h"
#include "network_4g.h"
#include "webrtc_mqtt.h"
#include "otaupgrade.h"
#include "driver/gpio.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_console.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <algorithm>
#include <cstdio>
#include <inttypes.h>

namespace {
constexpr gpio_num_t ADC_GATE = GPIO_NUM_9, EXT_N = GPIO_NUM_10, BACKUP_N = GPIO_NUM_47;
constexpr gpio_num_t CHARGING_N = GPIO_NUM_48, FULL_N = GPIO_NUM_1, CHARGE_PAUSE = GPIO_NUM_38;
constexpr adc_channel_t CHANNEL = ADC_CHANNEL_1; // ESP32-S3 ADC1 channel1 = GPIO2
adc_oneshot_unit_handle_t adc;
adc_cali_handle_t calibration;
TaskHandle_t task;
TaskHandle_t publish_task;
portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
power_monitor_snapshot_t latest = {false, false, false, -1, -1, -1, -1, -1, 0};
const char *source_name(int source) { return source == 0 ? "external" : source == 1 ? "battery" : "unknown"; }

int battery_voltage()
{
    if (!calibration) return -1;
    gpio_set_level(ADC_GATE, 1);
    // 150k/100k divider + 100nF: tau=6ms. Allow >6tau after the PMOS gate opens.
    vTaskDelay(pdMS_TO_TICKS(40));
    int samples[16]; bool ok = true;
    for (int &sample : samples) {
        int raw;
        if (adc_oneshot_read(adc, CHANNEL, &raw) != ESP_OK ||
            adc_cali_raw_to_voltage(calibration, raw, &sample) != ESP_OK) { ok = false; break; }
    }
    gpio_set_level(ADC_GATE, 0);
    if (!ok) return -1;
    std::sort(samples, samples + 16);
    int sum = 0;
    for (int i = 4; i < 12; ++i) sum += samples[i];
    int mv = (sum * 5 + 8) / 16; // trimmed mean × (150k+100k)/100k
    return mv >= 2500 && mv <= 4400 ? mv : -1;
}

void publish(const power_monitor_snapshot_t &s)
{
    // Local GPIO/ADC continue during calls. Never insert MQTT/AT operations in
    // the ringing, media or OTA path; keep only the newest snapshot.
    if (webrtc_get_call_state() != CALL_STATE_IDLE || ota_is_in_progress()) return;
    Mqtt *mqtt = Network4g::GetMqttInstance();
    if (!mqtt || !mqtt->IsConnected()) return;
    const app_config_t *cfg = app_config_get();
    char topic[160], body[512];
    std::snprintf(topic, sizeof(topic), "%s/%s/power", cfg->base_topic, cfg->device_id);
    int n = std::snprintf(body, sizeof(body),
        "{\"schema\":1,\"device\":\"%s\",\"uptime_ms\":%" PRId64
        ",\"source\":\"%s\",\"external_present\":%d,\"battery_mv\":%d"
        ",\"battery_percent\":%d,\"estimate\":true,\"calibrated\":%s,\"charging\":%d,\"charge_paused\":%s}",
        cfg->device_id, s.sampled_ms, source_name(s.source), s.external_present,
        s.battery_mv, s.battery_percent, s.calibrated ? "true" : "false",
        s.charging, s.charge_paused ? "true" : "false");
    if (n > 0 && n < (int)sizeof(body)) mqtt->Publish(topic, body, 0);
}

void monitor(void *)
{
    int64_t sampled = -1000;
    int last_source = -2, last_charge = -2;
    for (;;) {
        bool paused = webrtc_get_call_state() != CALL_STATE_IDLE || ota_is_in_progress();
        gpio_set_level(CHARGE_PAUSE, paused ? 1 : 0);
        int64_t now = esp_timer_get_time()/1000;
        if (now - sampled >= 1000) {
            power_monitor_snapshot_t s{};
            s.enabled = true; s.calibrated = calibration != nullptr; s.charge_paused = paused;
            s.battery_mv = battery_voltage();
            s.battery_percent = power_voltage_percent(s.battery_mv);
            s.external_present = gpio_get_level(EXT_N) == 0;
            s.source = power_actual_source(s.external_present, gpio_get_level(BACKUP_N) == 0);
            s.charging = power_charge_state(gpio_get_level(CHARGING_N) == 0,
                                           gpio_get_level(FULL_N) == 0, paused, s.battery_mv);
            s.sampled_ms = esp_timer_get_time()/1000; sampled = s.sampled_ms;
            portENTER_CRITICAL(&lock); latest = s; portEXIT_CRITICAL(&lock);
            if (s.source != last_source || s.charging != last_charge) {
                ESP_LOGI("POWER", "source=%s external=%d battery=%dmV estimate=%d%% charging=%d",
                         source_name(s.source), s.external_present, s.battery_mv, s.battery_percent, s.charging);
                last_source = s.source; last_charge = s.charging;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

void publish_latest(void *)
{
    int64_t sent = -30000;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        int64_t now = esp_timer_get_time()/1000;
        if (now-sent < 30000 || webrtc_get_call_state()!=CALL_STATE_IDLE || ota_is_in_progress()) continue;
        power_monitor_snapshot_t s; power_monitor_get_snapshot(&s);
        if (!s.enabled) continue;
        sent=now;
        publish(s); // AT waits cannot delay GPIO/ADC sampling or charge control.
    }
}

int status(int, char **)
{
    power_monitor_snapshot_t s; power_monitor_get_snapshot(&s);
    std::printf("enabled=%d calibrated=%d source=%s external_present=%d battery_mv=%d "
                "battery_percent_estimate=%d charging=%d charge_paused=%d sampled_ms=%" PRId64 "\n",
                s.enabled, s.calibrated, source_name(s.source), s.external_present, s.battery_mv,
                s.battery_percent, s.charging, s.charge_paused, s.sampled_ms);
    return 0;
}
} // namespace

extern "C" void power_monitor_get_snapshot(power_monitor_snapshot_t *s)
{
    if (!s) return;
    portENTER_CRITICAL(&lock); *s = latest; portEXIT_CRITICAL(&lock);
}

extern "C" esp_err_t power_monitor_register_console(void)
{
    esp_console_cmd_t cmd{};
    cmd.command = "power_status"; cmd.help = "V6 UPS actual supply, battery voltage and estimated level";
    cmd.func = status;
    return esp_console_cmd_register(&cmd);
}

extern "C" esp_err_t power_monitor_start(void)
{
    if (task) return ESP_OK;
    gpio_config_t output{};
    output.pin_bit_mask = (1ULL << ADC_GATE) | (1ULL << CHARGE_PAUSE); output.mode = GPIO_MODE_OUTPUT;
    esp_err_t ret = gpio_config(&output);
    if (ret != ESP_OK) return ret;
    gpio_set_level(ADC_GATE, 0); gpio_set_level(CHARGE_PAUSE, 0);
    gpio_config_t input{};
    input.pin_bit_mask = (1ULL << EXT_N) | (1ULL << BACKUP_N) | (1ULL << CHARGING_N) | (1ULL << FULL_N);
    input.mode = GPIO_MODE_INPUT; // physical 3.3V pull-ups; never connect these pins to 5V
    if ((ret = gpio_config(&input)) != ESP_OK) return ret;
    adc_oneshot_unit_init_cfg_t unit{}; unit.unit_id = ADC_UNIT_1; unit.ulp_mode = ADC_ULP_MODE_DISABLE;
    if ((ret = adc_oneshot_new_unit(&unit, &adc)) != ESP_OK) return ret;
    adc_oneshot_chan_cfg_t channel{}; channel.atten = ADC_ATTEN_DB_12; channel.bitwidth = ADC_BITWIDTH_DEFAULT;
    if ((ret = adc_oneshot_config_channel(adc, CHANNEL, &channel)) != ESP_OK) {
        adc_oneshot_del_unit(adc); adc = nullptr; return ret;
    }
    adc_cali_curve_fitting_config_t config{};
    config.unit_id = ADC_UNIT_1; config.chan = CHANNEL; config.atten = ADC_ATTEN_DB_12;
    config.bitwidth = ADC_BITWIDTH_DEFAULT;
    if (adc_cali_create_scheme_curve_fitting(&config, &calibration) != ESP_OK) {
        calibration = nullptr;
        ESP_LOGW("POWER", "ADC calibration unavailable; battery estimate remains unknown");
    }
    if (xTaskCreate(monitor, "power_monitor", 4096, nullptr, 1, &task) != pdPASS) {
        if (calibration) adc_cali_delete_scheme_curve_fitting(calibration);
        calibration = nullptr; adc_oneshot_del_unit(adc); adc = nullptr; return ESP_ERR_NO_MEM;
    }
    if (xTaskCreate(publish_latest, "power_publish", 8192, nullptr, 1, &publish_task) != pdPASS) {
        ESP_LOGW("POWER", "Telemetry task unavailable; local GPIO/ADC monitoring continues");
    }
    return ESP_OK;
}
