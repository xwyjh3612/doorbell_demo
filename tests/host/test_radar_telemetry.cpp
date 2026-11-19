#include <cassert>
#include <cstdio>
#include "webrtc_mqtt.h"
static call_state_t call_state=CALL_STATE_IDLE;
static bool upgrading;
extern "C" call_state_t webrtc_get_call_state(void){return call_state;}
bool ota_is_in_progress(void){return upgrading;}
#include "radar_telemetry_guard_under_test.inc"
int main(){
    assert(radar_telemetry_allowed());
    upgrading=true;assert(!radar_telemetry_allowed());upgrading=false;
    for(int i=CALL_STATE_OUTGOING;i<=CALL_STATE_RECONNECTING;i++){
        call_state=static_cast<call_state_t>(i);assert(!radar_telemetry_allowed());
    }
    call_state=CALL_STATE_IDLE;assert(radar_telemetry_allowed());
    puts("Radar upload guard: actual idle enum, all call phases, OTA and return to idle passed");
}
