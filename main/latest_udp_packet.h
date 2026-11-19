#pragma once

#include <mutex>
#include <string>

// One pending datagram only: a new packet replaces the old pending packet.
// Keep copying, allocating and freeing packet bytes outside the mailbox lock.
class LatestUdpPacket {
public:
    void publish(const std::string& data) {
        if (data.empty()) {
            return;
        }
        std::string replacement(data);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            pending_.swap(replacement);
        }
        // replacement now owns the discarded old packet; free it after unlocking.
    }

    bool take(std::string& packet) {
        // The nonblocking receive path must not wait for the publisher's lock.
        std::string received;
        {
            std::unique_lock<std::mutex> lock(mutex_, std::try_to_lock);
            if (!lock.owns_lock() || pending_.empty()) {
                return false;
            }
            // Transfer ownership instead of copying bytes while the producer writes.
            received.swap(pending_);
        }
        // Replace the caller's output outside the lock (including freeing its old
        // contents). New arrivals cannot modify the snapshot the caller now owns.
        packet.swap(received);
        return true;
    }

private:
    std::mutex mutex_;
    std::string pending_;
};
