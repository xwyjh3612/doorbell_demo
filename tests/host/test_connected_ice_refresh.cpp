#include <cassert>
#include <cstring>
#include <cstdlib>
#include <cstdio>
#include <initializer_list>
#include "webrtc_mqtt.h"
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
struct esp_peer_signaling_ice_info_t {
    struct {const char *stun_url, *user, *psw;} server_info;
    bool is_initiator;
};
struct mqtt_sig_t {
    char *ice_url = nullptr, *ice_user = nullptr, *ice_psw = nullptr;
    bool is_initiator = false;
    struct {int (*on_ice_info)(esp_peer_signaling_ice_info_t *,void *);void *ctx;} cfg;
};
static call_state_t phase;
extern "C" call_state_t webrtc_get_call_state(void){return phase;}
// Exercise allocation failure without changing the production function.
static int fail_allocation = 0, allocations = 0;
static char *copy_ice(const char *value) {
    if(++allocations==fail_allocation)return nullptr;
    size_t n=std::strlen(value)+1;char *result=static_cast<char *>(std::malloc(n));std::memcpy(result,value,n);return result;
}
#define strdup copy_ice
#include "connected_ice_refresh_under_test.inc"
#undef strdup
struct Peer {
    int reinitializations=0;
    const char *retained_url=nullptr;
    bool initiator=false;
};
static int received(esp_peer_signaling_ice_info_t *info,void *ctx){
    auto &peer=*static_cast<Peer *>(ctx);peer.reinitializations++;peer.retained_url=info->server_info.stun_url;peer.initiator=info->is_initiator;return 0;
}
int main(){
    Peer peer;mqtt_sig_t signal;signal.cfg={received,&peer};
    phase=CALL_STATE_IDLE;mqtt_sig_apply_ice(&signal,"stun:first.invalid","old-user","old-secret");assert(peer.reinitializations==1);
    char *url=signal.ice_url,*user=signal.ice_user,*password=signal.ice_psw;
    phase=CALL_STATE_CONNECTED;
    // Even changed credentials on recovery must not destroy the active call.
    mqtt_sig_apply_ice(&signal,"stun:refreshed.invalid","new-user","new-secret");
    assert(peer.reinitializations==1);assert(signal.ice_url==url && signal.ice_user==user && signal.ice_psw==password);
    assert(peer.retained_url==signal.ice_url && std::strcmp(peer.retained_url,"stun:first.invalid")==0);
    // A new answered/originated call still receives ICE, with its correct role.
    for(call_state_t state:{CALL_STATE_IDLE,CALL_STATE_INCOMING,CALL_STATE_INCOMING_CONNECTING,CALL_STATE_OUTGOING,CALL_STATE_OUTGOING_CONNECTING,CALL_STATE_RECONNECTING}){
        phase=state;signal.is_initiator=state==CALL_STATE_OUTGOING || state==CALL_STATE_OUTGOING_CONNECTING;
        int before=peer.reinitializations;mqtt_sig_apply_ice(&signal,"stun:next.invalid","next-user","next-secret");
        assert(peer.reinitializations==before+1 && peer.initiator==signal.is_initiator);
    }
    // Failed allocation cannot free the pointers retained by the existing peer.
    for(int failure=1;failure<=3;failure++){
        url=signal.ice_url;int before=peer.reinitializations;phase=CALL_STATE_IDLE;allocations=0;fail_allocation=failure;
        mqtt_sig_apply_ice(&signal,"stun:failed.invalid","next-user","next-secret");
        assert(signal.ice_url==url && peer.retained_url==url && peer.reinitializations==before);
    }
    free(signal.ice_url);free(signal.ice_user);free(signal.ice_psw);
    puts("PASS: connected ICE refresh preserves peer/config; new calls/roles and allocation failures remain valid");
}
