#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

// Only platform/framework types are replaced. The production send_ring
// function is extracted unchanged by run_host_tests.py.
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
using esp_peer_signaling_handle_t = void *;
struct esp_peer_signaling_ice_info_t {
    struct { const char *stun_url; const char *user; const char *psw; } server_info;
    bool is_initiator;
};
enum { ESP_PEER_SIGNALING_MSG_CUSTOMIZED = 1 };
struct esp_peer_signaling_msg_t { int type; uint8_t *data; int size; };
struct mqtt_sig_t {
    bool is_initiator;
    const char *ice_url;
    const char *ice_user;
    const char *ice_psw;
    struct {
        int (*on_ice_info)(esp_peer_signaling_ice_info_t *, void *);
        int (*on_msg)(esp_peer_signaling_msg_t *, void *);
        void *ctx;
    } cfg;
};
esp_peer_signaling_handle_t g_mqtt_sig_handle;
#include "outgoing_ring_under_test.inc"

struct PeerStub {
    bool cachedControlling = false;
    bool requireRoleRefresh = true;
    std::vector<int> events;
};
static int ice(esp_peer_signaling_ice_info_t *info, void *context) {
    auto &peer = *static_cast<PeerStub *>(context);
    assert(info->server_info.stun_url && info->server_info.user && info->server_info.psw);
    peer.cachedControlling = info->is_initiator;
    peer.events.push_back(1);
    return 0;
}
static int message(esp_peer_signaling_msg_t *message, void *context) {
    auto &peer = *static_cast<PeerStub *>(context);
    assert(message->type == ESP_PEER_SIGNALING_MSG_CUSTOMIZED);
    assert(std::string(reinterpret_cast<char *>(message->data), message->size) == "ACCEPT_CALL");
    if (peer.requireRoleRefresh) assert(peer.cachedControlling);
    peer.events.push_back(2);
    return 0;
}
int main() {
    PeerStub peer;
    mqtt_sig_t signal{false, "stun:relay.invalid:3478", "test", "test", {ice, message, &peer}};
    g_mqtt_sig_handle = &signal;
    // A prior answered call left the peer in controlled/callee mode.
    mqtt_sig_send_ring(nullptr);
    assert(signal.is_initiator && peer.cachedControlling);
    assert((peer.events == std::vector<int>{1, 2}));
    // Repeat after another answered call; no reboot or global reset required.
    peer.cachedControlling = false; peer.events.clear(); signal.is_initiator = false;
    mqtt_sig_send_ring("web_client_001");
    assert((peer.events == std::vector<int>{1, 2}));
    // Before ICE has arrived, do not fabricate credentials or crash.
    peer.events.clear(); peer.requireRoleRefresh = false; signal.ice_url = nullptr;
    mqtt_sig_send_ring(nullptr);
    assert((peer.events == std::vector<int>{2}));
    // A missing signaling instance cannot enable a peer.
    peer.events.clear(); g_mqtt_sig_handle = nullptr;
    mqtt_sig_send_ring(nullptr);
    assert(peer.events.empty());
    puts("PASS: outgoing role refresh after callee call, repeat, no ICE and no signaling");
}
