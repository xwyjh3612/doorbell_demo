#include <cassert>
#include <cstdio>
#include <initializer_list>
#include "../main/status_indicator_logic.h"

int main()
{
    assert(status_indicator_select(false, CALL_STATE_IDLE) == status_indicator_mode::offline);
    assert(status_indicator_select(true, CALL_STATE_IDLE) == status_indicator_mode::online);
    for (auto state : {CALL_STATE_OUTGOING, CALL_STATE_OUTGOING_CONNECTING,
                      CALL_STATE_INCOMING, CALL_STATE_INCOMING_CONNECTING,
                      CALL_STATE_RECONNECTING}) {
        assert(status_indicator_select(false, state) == status_indicator_mode::calling);
        assert(status_indicator_select(true, state) == status_indicator_mode::calling);
    }
    assert(status_indicator_select(false, CALL_STATE_CONNECTED) == status_indicator_mode::in_call);
    assert(status_indicator_select(true, CALL_STATE_CONNECTED) == status_indicator_mode::in_call);
    auto offline = status_indicator_color(status_indicator_mode::offline);
    auto online = status_indicator_color(status_indicator_mode::online);
    auto calling = status_indicator_color(status_indicator_mode::calling);
    assert(offline.red > 0 && offline.green == 0 && offline.blue == 0);
    assert(online.red == 0 && online.green > 0 && online.blue == 0);
    assert(calling.red == 0 && calling.green == 0 && calling.blue > 0);
    // Each observed cycle must contain a visible pulse AND a dark gap. Ensure
    // the online double flash remains distinct from slow/offline flashing.
    for (auto mode : {status_indicator_mode::offline, status_indicator_mode::online,
                      status_indicator_mode::calling, status_indicator_mode::in_call}) {
        int on = 0, off = 0, rising = 0; bool previous = false;
        for (uint64_t t = 0; t < 2000; t += 50) {
            bool lit = status_indicator_on(mode, t);
            if (lit) ++on; else ++off;
            if (lit && !previous) ++rising;
            previous = lit;
            assert(lit == status_indicator_on(mode, t + 2000));
            assert(lit == status_indicator_on(mode, (1ULL << 32) * 2000 + t));
        }
        assert(on > 0 && off > 0);
        if (mode == status_indicator_mode::calling) assert(rising == 8);
        if (mode == status_indicator_mode::online) assert(rising == 2 && on == 4);
    }
    std::puts("status indicator: call/offline/online selection, pulses and long uptime passed");
}
