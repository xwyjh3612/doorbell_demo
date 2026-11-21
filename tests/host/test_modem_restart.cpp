#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "webrtc_mqtt.h"
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
static int locks, restarts;
static int64_t clock_us;
static call_state_t phase = CALL_STATE_IDLE;
extern "C" call_state_t webrtc_get_call_state(void) { return phase; }
void voice_call_lock() { ++locks; }
void voice_call_unlock() { --locks; }
int64_t esp_timer_get_time() { return clock_us; }
struct AtModem {
    void Reboot() { assert(locks == 1 && phase == CALL_STATE_IDLE); ++restarts; }
};
namespace Network4g {
    static AtModem device;
    static bool available = true;
    AtModem* GetModemInstance() { return available ? &device : nullptr; }
}
#include "modem_restart_under_test.inc"
int main() {
    char command[] = "modem", restart[] = "restart", invalid[] = "invalid";
    char* args[] = {command, restart};
    char* bad_args[] = {command, invalid};
    assert(modem_cli(1, args) == 1 && modem_cli(2, bad_args) == 1);
    for (int p = CALL_STATE_OUTGOING; p <= CALL_STATE_RECONNECTING; ++p) {
        phase = static_cast<call_state_t>(p);
        assert(modem_cli(2, args) == 1 && locks == 0 && restarts == 0);
    }
    phase = CALL_STATE_IDLE; Network4g::available = false;
    assert(modem_cli(2, args) == 1 && locks == 0);
    Network4g::available = true;
    assert(modem_cli(2, args) == 0 && restarts == 1 && locks == 0);
    clock_us = 119999999;
    assert(modem_cli(2, args) == 1 && restarts == 1 && locks == 0);
    clock_us = 120000000;
    assert(modem_cli(2, args) == 0 && restarts == 2 && locks == 0);
    puts("PASS: explicit modem restart excludes every call phase and enforces 120s cooldown");
}
