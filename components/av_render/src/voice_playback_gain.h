#pragma once

#include <stddef.h>
#include <stdint.h>

// Work on the decoder's current mono PCM frame: no lookahead queue or allocation.
// Q12 gain: up to +18 dB for quiet speech, with 2 dB of digital peak headroom.
enum { VOICE_UNITY = 4096, VOICE_MAX_GAIN = 8 * VOICE_UNITY, VOICE_PEAK = 26000 };

static inline void voice_level_mono(int16_t *pcm, size_t count, unsigned rate, int *gain)
{
    if (!count || !rate) return;
    int peak = 0;
    for (size_t i = 0; i < count; ++i) {
        int s = pcm[i];
        int magnitude = s < 0 ? -s : s;
        if (magnitude > peak) peak = magnitude;
    }
    int target = peak <= VOICE_PEAK / (VOICE_MAX_GAIN / VOICE_UNITY) ? VOICE_MAX_GAIN : VOICE_PEAK * VOICE_UNITY / peak;
    // Release over ~200 ms. On a loud onset, ease down within 2 ms when the
    // samples permit; an abrupt full-scale transient must respect the ceiling immediately.
    int level = *gain;
    int step = (int)(VOICE_MAX_GAIN * 5U / rate) + 1;
    int attack = level > target ? (level - target) / (int)(rate / 500 + 1) + 1 : 0;
    for (size_t i = 0; i < count; ++i) {
        if (level > target) {
            level = level - attack > target ? level - attack : target;
            int magnitude = pcm[i] < 0 ? -(int)pcm[i] : pcm[i];
            if (magnitude * level > VOICE_PEAK * VOICE_UNITY)
                level = VOICE_PEAK * VOICE_UNITY / magnitude;
        } else if (level < target) {
            level = level + step < target ? level + step : target;
        }
        pcm[i] = (int16_t)((pcm[i] * level) / VOICE_UNITY);
    }
    *gain = level;
}
