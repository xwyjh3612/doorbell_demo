#pragma once
#include "udp.h"
#include <atomic>
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

// Experimental UDP transport. Keeps the existing application's latest-packet
// mailbox; send never waits for AT or grows a retry queue.
class VoiceUsbUdp final : public Udp {
public:
    VoiceUsbUdp();
    ~VoiceUsbUdp() override;
    bool Connect(const std::string& host,int port) override;
    void Disconnect() override;
    int Send(const std::string& data,int timeout_ms=-1) override;
    int GetLastError() override { return last_error_.load(); }
private:
    void receive();
    int fd_=-1;
    std::atomic<bool> running_{false};
    std::atomic<int> last_error_{0};
    EventGroupHandle_t stopped_=nullptr;
};
