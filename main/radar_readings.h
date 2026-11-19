#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    int activity, motion, breath, heart, distance_cm, bed, sleep_raw;
    int64_t breath_ms, heart_ms, distance_ms, motion_ms;
} radar_readings_t;

static inline void radar_readings_reset(radar_readings_t *r)
{
    *r = (radar_readings_t){.activity=-1, .motion=-1, .breath=-1, .heart=-1,
                           .distance_cm=-1, .bed=-1, .sleep_raw=-1};
}

// Called only after the wire parser validates length, checksum and tail.
// Unsupported values never replace an earlier valid measurement.
static inline void radar_readings_apply(radar_readings_t *r, const uint8_t *f,
                                        size_t size, int64_t now, bool vitals)
{
    if (size == 10 && f[2] == 5 && f[3] == 1 && f[6] == 15) {
        radar_readings_reset(r); return;
    }
    if (size == 10 && f[2] == 0x80 && f[3] == 1 && f[6] == 0) {
        radar_readings_reset(r); return;
    }
    if (size == 10 && f[2] == 0x80 && f[3] == 2 && f[6] <= 2) { r->activity = f[6]; }
    if (!vitals) { return; }
    if (size == 10 && f[2] == 0x80 && f[3] == 3 && f[6] <= 100) {
        r->motion = f[6]; r->motion_ms = now;
    } else if (size == 11 && f[2] == 0x80 && f[3] == 4) {
        r->distance_cm = (f[6] << 8) | f[7]; r->distance_ms = now;
    } else if (size == 10 && f[2] == 0x81 && f[3] == 2 && f[6] <= 35) {
        r->breath = f[6]; r->breath_ms = now;
    } else if (size == 10 && f[2] == 0x85 && f[3] == 2 &&
               (f[6] == 0 || (f[6] >= 60 && f[6] <= 120))) {
        r->heart = f[6]; r->heart_ms = now;
    } else if (size == 10 && f[2] == 0x84 && f[3] == 1 && f[6] <= 2) {
        r->bed = f[6];
    } else if (size == 10 && f[2] == 0x84 && f[3] == 2 && f[6] <= 3) {
        r->sleep_raw = f[6]; // Firmware revision not queried: no sleep classification.
    }
}
