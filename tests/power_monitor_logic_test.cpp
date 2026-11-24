#include <cassert>
#include <cstdio>
#include "../main/power_monitor_logic.h"
int main()
{
    // A plugged-in adapter does not override the mux's actual battery selection.
    assert(power_actual_source(true, true) == 1);
    assert(power_actual_source(false, true) == 1);
    assert(power_actual_source(true, false) == 0);
    assert(power_actual_source(false, false) == -1);
    assert(power_voltage_percent(-1) == -1);
    assert(power_voltage_percent(0) == -1);
    assert(power_voltage_percent(5000) == -1);
    assert(power_voltage_percent(3000) == 0);
    assert(power_voltage_percent(3800) == 60);
    assert(power_voltage_percent(4200) == 100);
    for (int mv = 2501; mv <= 4400; ++mv)
        assert(power_voltage_percent(mv) >= power_voltage_percent(mv-1));
    assert(power_charge_state(true, false, false, 3800) == 1);
    assert(power_charge_state(false, true, false, 4200) == 2);
    assert(power_charge_state(false, false, true, 3800) == 3);
    assert(power_charge_state(true, true, false, 3800) == -1);
    assert(power_charge_state(false, false, false, -1) == -1);
    std::puts("Power source / unknown voltage / estimate boundaries / charge status passed");
}
