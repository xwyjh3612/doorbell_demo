"""Checks for corrupt frames, repeated/overlapping snapshots and device restarts."""
import unittest
from telemetry import Telemetry, frames_in


def frame(control, command, payload):
    data = b"\x53\x59" + bytes([control, command]) + len(payload).to_bytes(2, "big") + payload
    return data + bytes([sum(data) % 256]) + b"\x54\x43"


def status(t, total, rx=6, ms=1000):
    t.feed(f"I ({ms}) RADAR_GPIO5: STATUS rx={rx} baud=115200 bytes={total} errors=0 header5359=0 level=1")


def history(t, data, total=None, rx=6, ms=1001):
    if total is None:
        total = len(data)
    t.feed(f"I ({ms}) RADAR_GPIO5: HISTORY rx={rx} baud=115200 saved={len(data)} total={total} last_ms={ms-1}")
    for start in range(0, len(data), 16):
        t.feed(f"I ({ms}) RADAR_GPIO5: {data[start:start+16].hex(' ')}")


class TelemetryTests(unittest.TestCase):
    def test_passive_status_summary_does_not_invent_rx_time(self):
        t = Telemetry()
        t.feed("I (5000) RADAR_GPIO5: STATUS rx=6 baud=115200 bytes=50 errors=0 "
               "header5359=5 level=1 valid=5 invalid=0 breaks=0 presence=1 last_presence_ms=4000 "
               "breath=16 heart=76 distance_cm=60 activity=1")
        snapshot = t.snapshot()
        self.assertEqual(16, snapshot["summary"]["breath"])
        self.assertEqual(5, snapshot["summary"]["valid"])
        self.assertTrue(snapshot["presence"])
        self.assertIsNone(snapshot["rx_age_s"])
        t.feed("I (6000) RADAR_GPIO5: STATUS rx=6 baud=115200 bytes=50 errors=0 "
               "header5359=5 level=1 valid=5 presence=-1 last_presence_ms=0 breath=-1 heart=-1")
        self.assertIsNone(t.presence)
        self.assertEqual(-1, t.summary["heart"])

    def test_corruption_and_recovery(self):
        good = frame(0x80, 1, b"\x01")
        bad = bytearray(good)
        bad[-3] ^= 1
        data = b"\x00\xff\x53\x59\x80\x01\xff\xff" + bad + good
        self.assertEqual([p for _, _, p in frames_in(data)], [good])

    def test_presence_and_repeated_snapshot(self):
        data = frame(5, 1, b"\x0f") + frame(0x80, 1, b"\x00") + frame(0x80, 1, b"\x01")
        t = Telemetry()
        status(t, len(data))
        history(t, data)
        history(t, data, ms=6000)
        self.assertEqual(t.valid_frames, 3)
        self.assertEqual(t.new_bytes, 0)
        self.assertTrue(t.presence)
        self.assertTrue(all(f["historical"] for f in t.frames))

    def test_overlapping_ring_snapshots_and_split_frame(self):
        a = frame(0x80, 1, b"\x00")
        b = frame(0x80, 1, b"\x01")
        t = Telemetry()
        status(t, 8)
        history(t, a[:8])
        self.assertEqual(t.valid_frames, 0)
        history(t, a + b, ms=3000)
        history(t, (a + b)[5:], total=len(a+b), ms=4000)
        self.assertEqual(t.valid_frames, 2)
        self.assertEqual(t.new_bytes, 12)
        self.assertTrue(t.presence)

    def test_reset_and_pin_change_invalidate_presence(self):
        occupied = frame(0x80, 1, b"\x01")
        t = Telemetry()
        status(t, 10, ms=50000)
        history(t, occupied, ms=50001)
        status(t, 0, ms=1000)
        self.assertIsNone(t.presence)
        history(t, occupied, ms=2000)
        self.assertEqual(t.valid_frames, 2)
        status(t, 0, rx=8, ms=3000)
        self.assertIsNone(t.presence)
        self.assertEqual(t.epoch, 2)

    def test_initialization_invalidates_prior_presence(self):
        t = Telemetry()
        status(t, 20)
        history(t, frame(0x80, 1, b"\x01") + frame(5, 1, b"\x0f"))
        self.assertIsNone(t.presence)

    def test_incomplete_and_nonpresence_data_stays_unknown(self):
        t = Telemetry()
        status(t, 12)
        history(t, b"\x00\xff" + frame(0x80, 1, b"\x02"))
        self.assertIsNone(t.presence)
        self.assertEqual(t.valid_frames, 1)

    def test_integrated_uart_error_invalidates_presence_without_new_bytes(self):
        t = Telemetry()
        status(t, 10)
        history(t, frame(0x80, 1, b"\x01"))
        self.assertTrue(t.presence)
        t.feed("I (2000) RADAR_GPIO5: STATUS rx=6 baud=115200 bytes=10 errors=1 "
               "header5359=1 level=1 valid=1 invalid=0 breaks=2 presence=-1 last_presence_ms=0")
        history(t, frame(0x80, 1, b"\x01"), ms=2001)
        self.assertIsNone(t.presence)
        self.assertEqual(t.breaks, 2)
        self.assertEqual(t.valid_frames, 1)


if __name__ == "__main__":
    unittest.main()
