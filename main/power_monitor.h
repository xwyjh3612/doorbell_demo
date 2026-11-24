#pragma once
#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool enabled;
    bool calibrated;
    bool charge_paused;
    int external_present;  // -1 unknown; 0 absent; 1 present (not voltage quality)
    int source;            // -1 unknown; 0 external; 1 battery (actual mux ST)
    int battery_mv;        // -1 invalid / calibration unavailable
    int battery_percent;   // -1 unknown; voltage estimate, not a fuel gauge
    int charging;          // -1 unknown; 0 idle; 1 charging; 2 full; 3 paused
    int64_t sampled_ms;
} power_monitor_snapshot_t;
esp_err_t power_monitor_start(void);
esp_err_t power_monitor_register_console(void);
void power_monitor_get_snapshot(power_monitor_snapshot_t *snapshot);
#ifdef __cplusplus
}
#endif
