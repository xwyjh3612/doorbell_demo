#pragma once
#include "esp_capture_audio_src_if.h"

#ifdef __cplusplus
extern "C" {
#endif
// Project-local source adapter. The wrapped official source remains responsible
// for AFE/VAD. One independent reader drains it even if encoding/network stalls.
esp_capture_audio_src_if_t *voice_new_latest_pcm_src(esp_capture_audio_src_if_t *source);
#ifdef __cplusplus
}
#endif
