#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

// R24D / R60ABD1 wire format: 53 59 ctrl cmd len_hi len_lo payload sum8 54 43.
// Bound untrusted lengths and preserve partial frames between UART reads.
#define RADAR_FRAME_CAPACITY 512
typedef struct {
    uint8_t data[RADAR_FRAME_CAPACITY];
    size_t used;
    uint32_t invalid_frames;
} radar_frame_parser_t;

typedef void (*radar_frame_callback_t)(void *ctx, const uint8_t *frame, size_t size);

static inline void radar_frame_parser_reset(radar_frame_parser_t *parser)
{
    parser->used = 0;
}

static inline void radar_frame_parser_feed(radar_frame_parser_t *parser,
                                           const uint8_t *data, size_t size,
                                           radar_frame_callback_t callback, void *ctx)
{
    for (size_t i = 0; i < size; ++i) {
        if (parser->used == sizeof(parser->data)) {
            memmove(parser->data, parser->data + 1, --parser->used);
        }
        parser->data[parser->used++] = data[i];
        size_t cursor = 0, retain = parser->used;
        while (cursor < parser->used) {
            if (parser->data[cursor] != 0x53) { ++cursor; continue; }
            if (cursor + 1 == parser->used) {
                if (cursor < retain) { retain = cursor; }
                break;
            }
            if (parser->data[cursor + 1] != 0x59) { ++cursor; continue; }
            if (parser->used - cursor < 6) {
                if (cursor < retain) { retain = cursor; }
                ++cursor;
                continue;
            }
            size_t payload = ((size_t)parser->data[cursor + 4] << 8) |
                             parser->data[cursor + 5];
            size_t length = payload + 9;
            if (length > sizeof(parser->data)) {
                ++parser->invalid_frames;
                ++cursor;
                continue;
            }
            if (parser->used - cursor < length) {
                // A bogus incomplete header must not hide a later valid frame.
                if (cursor < retain) { retain = cursor; }
                ++cursor;
                continue;
            }
            const uint8_t *frame = parser->data + cursor;
            uint8_t checksum = 0;
            for (size_t j = 0; j < length - 3; ++j) { checksum += frame[j]; }
            bool valid = frame[length - 2] == 0x54 && frame[length - 1] == 0x43 &&
                         frame[length - 3] == checksum;
            if (!valid) {
                ++parser->invalid_frames;
                ++cursor;
                continue;
            }
            callback(ctx, frame, length);
            cursor += length;
            retain = cursor;  // Discard any preceding corrupt/incomplete header.
        }
        if (retain) {
            memmove(parser->data, parser->data + retain, parser->used - retain);
            parser->used -= retain;
        }
    }
}

// -2: unrelated/unsupported frame, -1: confirmed radar initialization,
//  0: unoccupied, 1: occupied. Silence alone never changes this state.
static inline int radar_frame_presence(const uint8_t *frame, size_t size)
{
    if (size != 10 || frame[4] != 0 || frame[5] != 1) { return -2; }
    if (frame[2] == 5 && frame[3] == 1 && frame[6] == 0x0f) { return -1; }
    if (frame[2] == 0x80 && frame[3] == 1 && frame[6] <= 1) { return frame[6]; }
    return -2;
}
