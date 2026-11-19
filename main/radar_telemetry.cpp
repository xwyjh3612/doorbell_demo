#include "radar_presence.h"
#include "network_4g.h"
#include "app_config.h"
#include "webrtc_mqtt.h"
#include "otaupgrade.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdio>
#include <inttypes.h>

static TaskHandle_t telemetry_task;
static bool radar_telemetry_allowed(void)
{
    return webrtc_get_call_state() == CALL_STATE_IDLE && !ota_is_in_progress();
}
static int64_t age(int64_t now, int value, int64_t observed)
{
    return value >= 0 ? (now > observed ? now - observed : 0) : -1;
}

static void publish_latest(void *)
{
    int64_t sent_at = -5000;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        int64_t now = esp_timer_get_time() / 1000;
        // ML307 MQTT and media share an AT transport. Keep uploads out of
        // ringing, negotiation and active calls: UART sampling remains live.
        if (now - sent_at < 5000 || !radar_telemetry_allowed()) { continue; }
        Mqtt *mqtt = Network4g::GetMqttInstance();
        if (!mqtt || !mqtt->IsConnected()) { continue; }
        radar_presence_snapshot_t s;
        radar_presence_get_snapshot(&s);
        if (!s.enabled) { continue; }
        app_config_t *cfg = app_config_get();
        char topic[160], body[768];
        std::snprintf(topic, sizeof(topic), "%s/%s/telemetry", cfg->base_topic, cfg->device_id);
        const auto &r = s.readings;
        int length = std::snprintf(body, sizeof(body),
            "{\"schema\":1,\"device\":\"%s\",\"radar\":\"%s\",\"uptime_ms\":%" PRId64
            ",\"rx_age_ms\":%" PRId64 ",\"presence\":%d,\"activity\":%d,\"motion\":%d"
            ",\"motion_age_ms\":%" PRId64 ",\"breath\":%d,\"breath_age_ms\":%" PRId64
            ",\"heart\":%d,\"heart_age_ms\":%" PRId64 ",\"distance_cm\":%d"
            ",\"distance_age_ms\":%" PRId64 ",\"bed\":%d,\"sleep_raw\":%d"
            ",\"valid_frames\":%" PRIu64 ",\"uart_errors\":%" PRIu32 "}",
            cfg->device_id,
#if CONFIG_VOICE_RADAR_R60
            "r60abd1",
#else
            "r24d",
#endif
            now, s.received_bytes ? now - s.last_rx_ms : -1, s.presence, r.activity, r.motion,
            age(now, r.motion, r.motion_ms), r.breath, age(now, r.breath, r.breath_ms),
            r.heart, age(now, r.heart, r.heart_ms), r.distance_cm,
            age(now, r.distance_cm, r.distance_ms), r.bed, r.sleep_raw, s.valid_frames, s.uart_errors);
        sent_at = now; // Latest snapshot only: no backlog, retries or per-frame queue.
        if (length > 0 && length < (int)sizeof(body) && mqtt->Publish(topic, body, 0)) {
            ESP_LOGI("RADAR_TELEMETRY", "published model=%s frames=%" PRIu64,
#if CONFIG_VOICE_RADAR_R60
                     "r60abd1",
#else
                     "r24d",
#endif
                     s.valid_frames);
        }
    }
}

extern "C" esp_err_t radar_telemetry_start(void)
{
    if (telemetry_task) { return ESP_OK; }
    return xTaskCreate(publish_latest, "radar_publish", 4096, nullptr, 1, &telemetry_task) == pdPASS
        ? ESP_OK : ESP_ERR_NO_MEM;
}
