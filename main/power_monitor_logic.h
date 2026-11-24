#pragma once

// Li-ion 1S voltage-only estimate. Calibrate this table against the actual cell.
// Charging, temperature and load sag make this unsuitable as remaining runtime.
static inline int power_voltage_percent(int mv)
{
    const int volt[] = {3000, 3300, 3500, 3600, 3700, 3750, 3800, 3900, 4000, 4100, 4200};
    const int pct[]  = {   0,    3,    8,   15,   30,   45,   60,   75,   85,   95,  100};
    if (mv < 2500 || mv > 4400) return -1;
    if (mv <= volt[0]) return 0;
    for (unsigned i = 1; i < sizeof(volt)/sizeof(volt[0]); ++i) {
        if (mv <= volt[i]) return pct[i-1] + (mv-volt[i-1])*(pct[i]-pct[i-1])/(volt[i]-volt[i-1]);
    }
    return 100;
}

static inline int power_actual_source(bool external_present, bool backup_active)
{
    // ST is open drain: if the mux has no input, its pull-up is not proof of VIN1.
    if (backup_active) return 1;
    return external_present ? 0 : -1;
}

static inline int power_charge_state(bool active_low, bool full_low, bool paused, int battery_mv)
{
    if (battery_mv < 2500 || (active_low && full_low)) return -1;
    if (paused) return 3;
    if (active_low) return 1;
    if (full_low) return 2;
    return 0;
}
