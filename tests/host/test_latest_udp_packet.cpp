#include "latest_udp_packet.h"

#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <thread>

static std::string make_packet(uint32_t sequence) {
    // Alternate lengths across the small-string and heap-allocation boundaries.
    const size_t lengths[] = {8, 31, 160, 730, 1460, 4096};
    std::string packet(lengths[sequence % 6], static_cast<char>(sequence % 251));
    std::memcpy(&packet[0], &sequence, sizeof(sequence));
    return packet;
}

static uint32_t verify_packet(const std::string& packet) {
    assert(packet.size() >= sizeof(uint32_t));
    uint32_t sequence;
    std::memcpy(&sequence, packet.data(), sizeof(sequence));
    assert(packet == make_packet(sequence));
    return sequence;
}

static void test_empty_and_binary() {
    LatestUdpPacket mailbox;
    std::string result = "previous output";
    assert(!mailbox.take(result));
    assert(result == "previous output");
    mailbox.publish("");
    assert(!mailbox.take(result));
    const std::string binary("\0\xff\x01\0", 4);
    mailbox.publish(binary);
    assert(mailbox.take(result) && result == binary);
    assert(!mailbox.take(result));
}

static void test_burst_keeps_only_latest() {
    LatestUdpPacket mailbox;
    for (uint32_t sequence = 1; sequence <= 10000; ++sequence) {
        mailbox.publish(make_packet(sequence));
    }
    std::string packet;
    assert(mailbox.take(packet));
    assert(verify_packet(packet) == 10000);
    assert(!mailbox.take(packet)); // No queue of stale voice packets.
}

static void test_arrival_during_read_preserves_snapshot() {
    LatestUdpPacket mailbox;
    const std::string first = make_packet(101);
    mailbox.publish(first);
    std::string snapshot;
    assert(mailbox.take(snapshot));
    std::thread producer([&] {
        for (uint32_t sequence = 102; sequence <= 20000; ++sequence) {
            mailbox.publish(make_packet(sequence));
        }
    });
    // Read the old snapshot while the publisher repeatedly replaces its slot.
    for (unsigned i = 0; i < 10000; ++i) {
        assert(snapshot == first);
        std::this_thread::yield();
    }
    producer.join();
    assert(snapshot == first);
    assert(mailbox.take(snapshot)); // A nonempty output must not reinsert its old packet.
    assert(verify_packet(snapshot) == 20000);
    assert(!mailbox.take(snapshot));
}

static void test_concurrent_receive_and_overwrite() {
    LatestUdpPacket mailbox;
    constexpr uint32_t count = 100000;
    std::atomic_bool start{false}, finished{false};
    std::atomic<uint32_t> progress{0};
    std::thread producer([&] {
        while (!start.load()) std::this_thread::yield();
        for (uint32_t sequence = 1; sequence <= count; ++sequence) {
            mailbox.publish(make_packet(sequence));
            // Guarantee both tasks make progress during the stress scenario.
            if (sequence % 1000 == 0) {
                while (progress.load() < sequence) std::this_thread::yield();
            }
        }
        finished.store(true);
    });
    start.store(true);
    uint32_t last = 0;
    size_t received = 0;
    while (!finished.load() || last < count) {
        std::string packet;
        if (mailbox.take(packet)) {
            uint32_t sequence = verify_packet(packet);
            assert(sequence > last); // Gaps are intentional drops; no duplicates/reordering.
            last = sequence;
            ++received;
            progress.store(sequence);
        } else {
            std::this_thread::yield();
        }
    }
    producer.join();
    std::string packet;
    assert(!mailbox.take(packet));
    assert(received >= 100);
    std::printf("Concurrent overwrite: %zu intact packets read from %u arrivals (gaps allowed)\n",
                received, count);
}

int main() {
    test_empty_and_binary();
    test_burst_keeps_only_latest();
    test_arrival_during_read_preserves_snapshot();
    test_concurrent_receive_and_overwrite();
    std::puts("PASS: 4 latest UDP packet scenarios");
}
