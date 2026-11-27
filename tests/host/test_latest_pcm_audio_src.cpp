#include <atomic>
#include <cassert>
#include <cstring>
#include <cstdio>
#include "latest_pcm_audio_src.h"
#include "freertos/task.h"

struct FakeSource {
    esp_capture_audio_src_if_t api{};
    std::atomic<int> frames{0}, in_read{0};
    std::atomic<bool> block{false}, vad{false}, fail{false};
    bool active = false;
    int stops = 0, closes = 0;
    FakeSource() {
        api.open = [](auto *) { return ESP_CAPTURE_ERR_OK; };
        api.get_support_codecs = [](auto *, const esp_capture_format_id_t **c, uint8_t *n) {
            static const esp_capture_format_id_t pcm = ESP_CAPTURE_FMT_ID_PCM;
            *c = &pcm; *n = 1; return ESP_CAPTURE_ERR_OK;
        };
        api.negotiate_caps = [](auto *, auto *in, auto *out) { *out = *in; return ESP_CAPTURE_ERR_OK; };
        api.start = [](auto *p) { auto *s = reinterpret_cast<FakeSource *>(p); assert(!s->active); s->active = true; return ESP_CAPTURE_ERR_OK; };
        api.read_frame = [](auto *p, auto *f) {
            auto *s = reinterpret_cast<FakeSource *>(p);
            assert(s->active && s->in_read.fetch_add(1) == 0);
            while (s->block.load()) vTaskDelay(1);
            vTaskDelay(2);
            int seq = ++s->frames;
            std::memset(f->data, seq & 255, f->size);
            f->pts = seq;
            if (s->vad) f->size = 0;
            --s->in_read;
            return s->fail ? ESP_CAPTURE_ERR_INTERNAL : ESP_CAPTURE_ERR_OK;
        };
        api.stop = [](auto *p) { auto *s = reinterpret_cast<FakeSource *>(p); assert(s->in_read == 0); s->active = false; ++s->stops; return ESP_CAPTURE_ERR_OK; };
        api.close = [](auto *p) { auto *s = reinterpret_cast<FakeSource *>(p); assert(!s->active && s->in_read == 0); ++s->closes; return ESP_CAPTURE_ERR_OK; };
    }
};
int main() {
    assert(!voice_new_latest_pcm_src(nullptr));
    FakeSource source;
    auto *pcm = voice_new_latest_pcm_src(&source.api);
    assert(pcm);
    uint8_t bytes[4096];
    auto read = [&](int size = 320) {
        esp_capture_stream_frame_t f{ESP_CAPTURE_STREAM_TYPE_AUDIO, 0, bytes, size};
        assert(pcm->read_frame(pcm, &f) == ESP_CAPTURE_ERR_OK);
        if (f.size) {
            assert(f.size == size);
            for (int i = 0; i < f.size; ++i) assert(bytes[i] == (f.pts & 255));
        }
        return f;
    };
    assert(pcm->start(pcm) == ESP_CAPTURE_ERR_INVALID_STATE);
    assert(pcm->open(pcm) == ESP_CAPTURE_ERR_OK);
    assert(pcm->start(pcm) == ESP_CAPTURE_ERR_OK);
    read();
    auto before = source.frames.load();
    vTaskDelay(500); // No consumer: producer MUST keep draining AFE, no backlog.
    assert(source.frames - before >= 8); // Windows host timer may have 15ms granularity.
    auto latest = read();
    assert(latest.size == 320 && source.frames - int(latest.pts) < 3);
    for (int i = 0; i < 40; ++i) read(); // Owned snapshots cannot tear/reuse scratch.
    esp_capture_stream_frame_t wrong{ESP_CAPTURE_STREAM_TYPE_AUDIO, 0, bytes, 640};
    assert(pcm->read_frame(pcm, &wrong) == ESP_CAPTURE_ERR_NOT_SUPPORTED);
    source.vad = true;
    vTaskDelay(80);
    assert(read().size == 0);
    source.vad = false;
    vTaskDelay(80);
    assert(read().size == 320);
    // Hung source: consumer wait is bounded and old PCM expires. Teardown must
    // preserve the live source instead of destroying AFE beneath its reader.
    source.block = true;
    vTaskDelay(150);
    assert(read().size == 0);
    assert(pcm->stop(pcm) == ESP_CAPTURE_ERR_TIMEOUT);
    assert(source.active && source.stops == 0 && source.closes == 0);
    source.block = false;
    vTaskDelay(20);
    assert(pcm->close(pcm) == ESP_CAPTURE_ERR_OK);
    host_join_tasks();
    assert(source.stops == 1 && source.closes == 1);
    for (int i = 0; i < 20; ++i) {
        assert(pcm->open(pcm) == ESP_CAPTURE_ERR_OK);
        assert(pcm->start(pcm) == ESP_CAPTURE_ERR_OK);
        if (i % 2) read(640); // Renegotiated size on a NEW run is valid.
        assert(pcm->close(pcm) == ESP_CAPTURE_ERR_OK); // Includes no-first-read stop.
        host_join_tasks();
    }
    assert(pcm->open(pcm) == ESP_CAPTURE_ERR_OK);
    source.fail = true;
    assert(pcm->start(pcm) == ESP_CAPTURE_ERR_OK);
    esp_capture_stream_frame_t error{ESP_CAPTURE_STREAM_TYPE_AUDIO, 0, bytes, 320};
    assert(pcm->read_frame(pcm, &error) == ESP_CAPTURE_ERR_INTERNAL);
    assert(pcm->close(pcm) == ESP_CAPTURE_ERR_OK);
    host_join_tasks();
    source.fail = false;
    assert(pcm->open(pcm) == ESP_CAPTURE_ERR_OK);
    host_task_failure = true;
    assert(pcm->start(pcm) == ESP_CAPTURE_ERR_NO_RESOURCES);
    assert(pcm->close(pcm) == ESP_CAPTURE_ERR_OK);
    std::puts("Latest PCM: stalled consumer, ownership, VAD, expiry, errors, safe stop and 20 restarts passed");
}
