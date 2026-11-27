#include "latest_pcm_audio_src.h"
#include <atomic>
#include <cstring>
#include <new>
#include <initializer_list>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_timer.h"

namespace {
constexpr int kMaxBytes = 4096;
constexpr int kReadWaitMs = 40;
constexpr int kStopWaitMs = 2000;
constexpr int64_t kMaxAgeUs = 100000;
const char *TAG = "LATEST_PCM";

struct LatestSource {
    esp_capture_audio_src_if_t api{}; // Interface is the first member.
    esp_capture_audio_src_if_t *source = nullptr;
    SemaphoreHandle_t lock = nullptr, request = nullptr, ready = nullptr, exited = nullptr;
    std::atomic<bool> running{false};
    bool started = false, opened = false;
    // Protected by lock. Producer never holds it while reading the official AFE.
    int requested = 0, size = 0;
    uint32_t pts = 0, overwritten = 0;
    int64_t published = 0;
    bool pending = false;
    esp_capture_err_t error = ESP_CAPTURE_ERR_OK;
    uint8_t scratch[kMaxBytes]{}, latest[kMaxBytes]{};
};
LatestSource *self(esp_capture_audio_src_if_t *p) { return reinterpret_cast<LatestSource *>(p); }
void take(LatestSource *s) { xSemaphoreTake(s->lock, portMAX_DELAY); }
void give(LatestSource *s) { xSemaphoreGive(s->lock); }

void drain(void *arg)
{
    auto *s = static_cast<LatestSource *>(arg);
    // Let the encoder choose its actual frame size, rather than assuming 10/20ms.
    xSemaphoreTake(s->request, portMAX_DELAY);
    take(s);
    const int bytes = s->requested;
    give(s);
    while (s->running.load() && bytes > 0) {
        esp_capture_stream_frame_t frame{};
        frame.stream_type = ESP_CAPTURE_STREAM_TYPE_AUDIO;
        frame.data = s->scratch;
        frame.size = bytes;
        auto ret = s->source->read_frame(s->source, &frame);
        if (!s->running.load()) break;
        take(s);
        if (ret != ESP_CAPTURE_ERR_OK || (frame.size != 0 && frame.size != bytes)) {
            s->error = ret != ESP_CAPTURE_ERR_OK ? ret : ESP_CAPTURE_ERR_INTERNAL;
            give(s);
            xSemaphoreGive(s->ready);
            break;
        }
        if (s->pending && s->size > 0) ++s->overwritten;
        if (frame.size) std::memcpy(s->latest, frame.data, frame.size);
        s->size = frame.size; // Preserve official VAD's empty-frame behavior.
        s->pts = frame.pts;
        s->published = esp_timer_get_time();
        s->pending = true;
        give(s);
        xSemaphoreGive(s->ready); // Binary notification, never a PCM backlog.
        // Cached chunks/VAD can return immediately; yield to feed and other tasks.
        vTaskDelay(1);
    }
    xSemaphoreGive(s->exited);
    vTaskDelete(nullptr); // No accesses to s after the exit notification.
}

esp_capture_err_t open(esp_capture_audio_src_if_t *p)
{
    auto *s = self(p);
    if (s->started) return ESP_CAPTURE_ERR_INVALID_STATE;
    auto ret = s->source->open(s->source);
    if (ret == ESP_CAPTURE_ERR_OK) s->opened = true;
    return ret;
}
esp_capture_err_t codecs(esp_capture_audio_src_if_t *p, const esp_capture_format_id_t **c, uint8_t *n)
{ auto *s = self(p); return s->source->get_support_codecs(s->source, c, n); }
esp_capture_err_t fixed(esp_capture_audio_src_if_t *p, const esp_capture_audio_info_t *c)
{
    auto *s = self(p);
    return s->source->set_fixed_caps ? s->source->set_fixed_caps(s->source, c) : ESP_CAPTURE_ERR_NOT_SUPPORTED;
}
esp_capture_err_t negotiate(esp_capture_audio_src_if_t *p, esp_capture_audio_info_t *in, esp_capture_audio_info_t *out)
{
    auto *s = self(p);
    if (s->started) return ESP_CAPTURE_ERR_INVALID_STATE;
    return s->source->negotiate_caps(s->source, in, out);
}
esp_capture_err_t start(esp_capture_audio_src_if_t *p)
{
    auto *s = self(p);
    if (!s->opened || s->started) return ESP_CAPTURE_ERR_INVALID_STATE;
    take(s);
    s->requested = s->size = 0;
    s->pending = false;
    s->overwritten = 0;
    s->error = ESP_CAPTURE_ERR_OK;
    give(s);
    xSemaphoreTake(s->request, 0);
    xSemaphoreTake(s->ready, 0);
    xSemaphoreTake(s->exited, 0);
    auto ret = s->source->start(s->source);
    if (ret != ESP_CAPTURE_ERR_OK) return ret;
    s->started = true;
    s->running.store(true);
    if (xTaskCreatePinnedToCore(drain, "AFE_FETCH", 8192, s, 16, nullptr, 0) != pdPASS) {
        s->running.store(false);
        s->source->stop(s->source);
        s->started = false;
        return ESP_CAPTURE_ERR_NO_RESOURCES;
    }
    ESP_LOGI(TAG, "Independent AFE reader started; latest PCM only");
    return ESP_CAPTURE_ERR_OK;
}
esp_capture_err_t read(esp_capture_audio_src_if_t *p, esp_capture_stream_frame_t *f)
{
    auto *s = self(p);
    if (!f || !f->data || f->size <= 0 || f->size > kMaxBytes || (f->size & 1)) return ESP_CAPTURE_ERR_INVALID_ARG;
    if (!s->running.load()) return ESP_CAPTURE_ERR_INVALID_STATE;
    take(s);
    if (s->requested && s->requested != f->size) {
        give(s);
        return ESP_CAPTURE_ERR_NOT_SUPPORTED; // No changing buffer contracts mid-run.
    }
    bool first = !s->requested;
    s->requested = f->size;
    give(s);
    if (first) xSemaphoreGive(s->request);
    xSemaphoreTake(s->ready, pdMS_TO_TICKS(kReadWaitMs));
    take(s);
    auto ret = s->error;
    if (ret == ESP_CAPTURE_ERR_OK) {
        if (s->pending && esp_timer_get_time() - s->published <= kMaxAgeUs) {
            if (s->size) std::memcpy(f->data, s->latest, s->size);
            f->size = s->size;
            f->pts = s->pts;
        } else {
            f->size = 0; // Bounded wait lets GMF's capture thread stop safely.
        }
        s->pending = false;
    }
    give(s);
    return ret;
}
esp_capture_err_t stop(esp_capture_audio_src_if_t *p)
{
    auto *s = self(p);
    if (!s->started) return ESP_CAPTURE_ERR_OK;
    s->running.store(false);
    xSemaphoreGive(s->request);
    xSemaphoreGive(s->ready);
    if (xSemaphoreTake(s->exited, pdMS_TO_TICKS(kStopWaitMs)) != pdTRUE) {
        // Official stop destroys AFE/VAD resources. Never call it under a reader.
        ESP_LOGE(TAG, "AFE reader stop timeout; preserving live source resources");
        return ESP_CAPTURE_ERR_TIMEOUT;
    }
    auto ret = s->source->stop(s->source);
    s->started = false;
    ESP_LOGI(TAG, "AFE reader stopped; overwritten old PCM frames=%lu", (unsigned long)s->overwritten);
    return ret;
}
esp_capture_err_t close(esp_capture_audio_src_if_t *p)
{
    auto *s = self(p);
    auto ret = stop(p);
    if (ret != ESP_CAPTURE_ERR_OK) return ret;
    if (!s->opened) return ESP_CAPTURE_ERR_OK;
    ret = s->source->close(s->source);
    if (ret == ESP_CAPTURE_ERR_OK) s->opened = false;
    // Capture reuses source objects across calls; retain the adapter like the
    // official source. Nothing can free buffers/semaphores under a live reader.
    return ret;
}
}

extern "C" esp_capture_audio_src_if_t *voice_new_latest_pcm_src(esp_capture_audio_src_if_t *source)
{
    if (!source || !source->open || !source->get_support_codecs || !source->negotiate_caps ||
        !source->start || !source->read_frame || !source->stop || !source->close) return nullptr;
    auto *s = new (std::nothrow) LatestSource;
    if (!s) return nullptr;
    s->source = source;
    s->lock = xSemaphoreCreateMutex();
    s->request = xSemaphoreCreateBinary();
    s->ready = xSemaphoreCreateBinary();
    s->exited = xSemaphoreCreateBinary();
    if (!s->lock || !s->request || !s->ready || !s->exited) {
        for (auto sem : {s->lock, s->request, s->ready, s->exited}) if (sem) vSemaphoreDelete(sem);
        delete s;
        return nullptr;
    }
    s->api.open = open;
    s->api.get_support_codecs = codecs;
    s->api.set_fixed_caps = fixed;
    s->api.negotiate_caps = negotiate;
    s->api.start = start;
    s->api.read_frame = read;
    s->api.stop = stop;
    s->api.close = close;
    return &s->api;
}
