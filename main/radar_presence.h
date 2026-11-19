#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "radar_readings.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool enabled;
    int presence; // -1 unknown, 0 unoccupied, 1 occupied (last valid report)
    uint64_t received_bytes;
    uint64_t valid_frames;
    uint64_t header_candidates;
    uint32_t uart_errors;
    uint32_t uart_breaks;
    uint32_t invalid_frames;
    int64_t last_rx_ms;
    int64_t last_presence_ms;
    radar_readings_t readings;
} radar_presence_snapshot_t;

// Receiver never drives radar TX or starts calls. Telemetry runs separately.
esp_err_t radar_presence_start(void);
esp_err_t radar_presence_register_console(void);
void radar_presence_get_snapshot(radar_presence_snapshot_t *snapshot);
esp_err_t radar_telemetry_start(void);

#ifdef __cplusplus
}
#endif
