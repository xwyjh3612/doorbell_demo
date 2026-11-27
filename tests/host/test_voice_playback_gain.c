#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "voice_playback_gain.h"

int main(void)
{
    int16_t pcm[320];
    const unsigned rates[] = {8000, 16000, 24000, 32000, 48000};
    for (size_t k = 0; k < sizeof(rates) / sizeof(rates[0]); ++k) {
        unsigned rate = rates[k];
        int gain = VOICE_MAX_GAIN;
        for (int i = 0; i < 320; ++i) pcm[i] = i % 2 ? -1200 : 1200;
        voice_level_mono(pcm, 320, rate, &gain);
        assert(pcm[0] == 9600 && pcm[319] == -9600);

        // The transient can land anywhere, including the very first sample.
        for (int pos = 0; pos < 32; ++pos) {
            gain = VOICE_MAX_GAIN;
            for (int i = 0; i < 320; ++i) pcm[i] = i < pos ? 2000 : (i % 2 ? -32768 : 32767);
            voice_level_mono(pcm, 320, rate, &gain);
            for (int i = 0; i < 320; ++i) assert(pcm[i] >= -VOICE_PEAK && pcm[i] <= VOICE_PEAK);
        }
        int after_peak = gain;
        for (int n = 0; n < 50; ++n) {
            for (int i = 0; i < 320; ++i) pcm[i] = 1234;
            voice_level_mono(pcm, 320, rate, &gain);
            if (!n) assert(pcm[0] < 1300 && gain > after_peak && gain < VOICE_MAX_GAIN);
        }
        assert(gain == VOICE_MAX_GAIN && pcm[319] == 8 * 1234);
        for (int i = 0; i < 320; ++i) pcm[i] = 0;
        voice_level_mono(pcm, 320, rate, &gain);
        for (int i = 0; i < 320; ++i) assert(pcm[i] == 0);
    }
    puts("Quiet speech +18.06 dB; transients bounded; release recovers; silence preserved.");
    return 0;
}
