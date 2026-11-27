#pragma once
#include "webrtc_mqtt.h"
#include <stdint.h>

enum class status_indicator_mode { offline, online, calling, in_call };

struct status_indicator_rgb { uint8_t red, green, blue; };

// Low brightness: the selected channel uses about 12mA * 16/255 average.
static inline status_indicator_rgb status_indicator_color(status_indicator_mode mode)
{
    switch (mode) {
    case status_indicator_mode::offline: return {16, 0, 0};
    case status_indicator_mode::online: return {0, 16, 0};
    case status_indicator_mode::calling:
    case status_indicator_mode::in_call: return {0, 0, 16};
    }
    return {0, 0, 0};
}

static inline status_indicator_mode status_indicator_select(bool mqtt_ready, call_state_t call)
{
    if (call == CALL_STATE_CONNECTED) return status_indicator_mode::in_call;
    if (call != CALL_STATE_IDLE) return status_indicator_mode::calling;
    return mqtt_ready ? status_indicator_mode::online : status_indicator_mode::offline;
}

// Every mode has an off interval so a stopped task does not resemble a normal
// steady light. This is a status indication, not an independent watchdog.
static inline bool status_indicator_on(status_indicator_mode mode, uint64_t elapsed_ms)
{
    switch (mode) {
    case status_indicator_mode::offline:
        return elapsed_ms % 1000 < 250;
    case status_indicator_mode::online: {
        const unsigned phase = elapsed_ms % 2000;
        return phase < 100 || (phase >= 250 && phase < 350);
    }
    case status_indicator_mode::calling:
        return elapsed_ms % 250 < 100;
    case status_indicator_mode::in_call:
        return elapsed_ms % 1000 < 900;
    }
    return false;
}
