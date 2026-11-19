#include <assert.h>
#include <stdio.h>
#include "radar_frame_parser.h"

static const uint8_t occupied[] = {0x53,0x59,0x80,1,0,1,1,0x2f,0x54,0x43};
static const uint8_t empty[] = {0x53,0x59,0x80,1,0,1,0,0x2e,0x54,0x43};
static const uint8_t init[] = {0x53,0x59,5,1,0,1,0x0f,0xc2,0x54,0x43};
static int frames, presence;
static void receive(void *ctx, const uint8_t *frame, size_t size)
{
    (void)ctx;
    ++frames;
    int result = radar_frame_presence(frame, size);
    if (result != -2) { presence = result; }
}
static void feed(radar_frame_parser_t *p, const uint8_t *data, size_t size)
{
    radar_frame_parser_feed(p, data, size, receive, NULL);
    assert(p->used <= RADAR_FRAME_CAPACITY);
}
int main(void)
{
    // Real captured frames, split at every possible UART boundary.
    for (size_t split = 0; split <= sizeof(occupied); ++split) {
        radar_frame_parser_t p = {0}; frames = 0; presence = -1;
        feed(&p, occupied, split); feed(&p, occupied + split, sizeof(occupied) - split);
        assert(frames == 1 && presence == 1 && p.used == 0);
    }
    radar_frame_parser_t p = {0}; frames = 0; presence = -1;
    feed(&p, empty, sizeof(empty)); feed(&p, occupied, sizeof(occupied));
    feed(&p, init, sizeof(init));
    assert(frames == 3 && presence == -1);
    // Bad checksum/tail and impossible or incomplete lengths cannot block recovery.
    uint8_t bad[sizeof(occupied)]; memcpy(bad, occupied, sizeof(bad)); bad[7] ^= 1;
    feed(&p, bad, sizeof(bad));
    memcpy(bad, occupied, sizeof(bad)); bad[9] = 0;
    feed(&p, bad, sizeof(bad));
    const uint8_t garbage[] = {0x53,0x59,0x80,1,0xff,0xff,0x53,0x59,0x80,1,0,100};
    feed(&p, garbage, sizeof(garbage)); feed(&p, occupied, sizeof(occupied));
    assert(frames == 4 && presence == 1 && p.invalid_frames >= 3);
    // Noise including repeated headers stays bounded and never guesses presence.
    uint8_t noise[2048]; memset(noise, 0x53, sizeof(noise));
    feed(&p, noise, sizeof(noise)); assert(frames == 4 && presence == 1);
    feed(&p, empty, sizeof(empty)); assert(frames == 5 && presence == 0);
    // A UART error/reset must discard a partial frame from before the error.
    feed(&p, occupied, 5); radar_frame_parser_reset(&p);
    feed(&p, occupied + 5, 5); assert(frames == 5);
    feed(&p, occupied, sizeof(occupied)); assert(frames == 6 && presence == 1);
    // Unsupported presence value must not become occupied/unoccupied.
    memcpy(bad, occupied, sizeof(bad)); bad[6] = 2; bad[7] = 0x30;
    feed(&p, bad, sizeof(bad)); assert(frames == 7 && presence == 1);
    // The maximum accepted length fits exactly; byte-wise delivery stays bounded.
    uint8_t maximum[RADAR_FRAME_CAPACITY]; memset(maximum, 0xaa, sizeof(maximum));
    maximum[0] = 0x53; maximum[1] = 0x59; maximum[2] = 0x81; maximum[3] = 1;
    maximum[4] = 1; maximum[5] = 0xf7; // 503-byte payload, 512-byte frame
    uint8_t sum = 0;
    for (size_t i = 0; i < sizeof(maximum) - 3; ++i) { sum += maximum[i]; }
    maximum[sizeof(maximum)-3] = sum;
    maximum[sizeof(maximum)-2] = 0x54; maximum[sizeof(maximum)-1] = 0x43;
    for (size_t i = 0; i < sizeof(maximum); ++i) { feed(&p, maximum + i, 1); }
    assert(frames == 8 && presence == 1 && p.used == 0);
    puts("Radar parser: captured frames, all split boundaries, corruption, recovery, noise, reset and unknown values passed");
    return 0;
}
