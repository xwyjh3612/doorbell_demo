#include <cassert>
#include <cstdio>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#define ESP_LOGI(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
using EventGroupHandle_t = unsigned*;
enum { ML307_UDP_DISCONNECTED=1, ML307_UDP_ERROR=2,
       ML307_UDP_CONNECTED=4, ML307_UDP_SEND_COMPLETE=8, ML307_UDP_INITIALIZED=16 };
void xEventGroupSetBits(EventGroupHandle_t event, unsigned bits) { *event |= bits; }
void xEventGroupClearBits(EventGroupHandle_t event, unsigned bits) { *event &= ~bits; }
struct AtArgumentValue { int int_value=0; std::string string_value; };
struct AtUart {
    bool receiving=false;
    unsigned commands=0;
    std::string DecodeHex(const std::string& hex) { return hex; }
    bool SendCommand(const std::string&, unsigned) {
        if (receiving) throw std::logic_error("AT command from locked UART callback would deadlock");
        ++commands;
        return true;
    }
};
struct Ml307Udp {
    std::shared_ptr<AtUart> at_uart_=std::make_shared<AtUart>();
    int udp_id_=2, last_error_=0;
    bool connected_=true, instance_active_=true;
    unsigned events=0;
    EventGroupHandle_t event_group_handle_=&events;
    std::function<void(const std::string&)> message_callback_;
    void handleUrc(const std::string&, const std::vector<AtArgumentValue>&);
    void Disconnect();
};
#include "udp_fifo_under_test.inc"

int main() {
    Ml307Udp udp;
    udp.at_uart_->receiving=true;
    // A hardware overrun loses UART bytes, not the UDP socket in the modem.
    // The actual production callback must return without recursively sending
    // an AT command while the receiver's callback mutex is held.
    for (int i=0;i<10;++i) udp.handleUrc("FIFO_OVERFLOW", {});
    assert(udp.events & ML307_UDP_ERROR);
    assert(udp.connected_ && udp.instance_active_);
    assert(udp.at_uart_->commands==0);
    std::string received;
    udp.message_callback_=[&](const std::string& data){received=data;};
    udp.handleUrc("MIPURC", {{0,"rudp"},{2,""},{4,""},{0,"next"}});
    assert(received=="next");
    udp.handleUrc("MIPCLOSE", {{2,""}});
    assert(!udp.connected_ && !udp.instance_active_);
    assert(udp.events & ML307_UDP_DISCONNECTED);
    assert(udp.at_uart_->commands==0);
    // Explicit close outside the receive callback still uses the original AT
    // command; the fix must not disable normal teardown.
    udp.connected_=udp.instance_active_=true;
    udp.at_uart_->receiving=false;
    udp.Disconnect();
    assert(udp.at_uart_->commands==1);
    assert(!udp.connected_ && !udp.instance_active_);
    std::puts("PASS: UDP FIFO loss does not recurse into AT or close the socket; receive and explicit close remain valid");
}
