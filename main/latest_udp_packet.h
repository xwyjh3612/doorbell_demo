#pragma once

#include <atomic>
#include <memory>
#include <new>
#include <string>

// One pending datagram only: a new packet replaces the old pending packet.
// Publish/take transfer exclusive ownership with one atomic pointer exchange.
// The ESP-IDF toolchain may use a short critical section for that exchange;
// allocation, string copies and deletion stay outside it. There is no mailbox
// task mutex that a preempted reader could hold while the UART callback waits.
class LatestUdpPacket {
public:
    ~LatestUdpPacket() {
        delete pending_.exchange(nullptr, std::memory_order_acq_rel);
    }

    void publish(const std::string& data) {
        if (data.empty()) {
            return;
        }
        auto *replacement = new (std::nothrow) std::string(data);
        if (!replacement) {
            return;
        }
        // Only this publisher owns the overwritten packet. A reader that took
        // it first removes it from the slot and keeps its bytes independently.
        delete pending_.exchange(replacement, std::memory_order_acq_rel);
    }

    bool take(std::string& packet) {
        std::unique_ptr<std::string> received(
            pending_.exchange(nullptr, std::memory_order_acq_rel));
        if (!received) {
            return false;
        }
        packet.swap(*received);
        return true;
    }

private:
    std::atomic<std::string *> pending_{nullptr};
};
