"""Protocol and session checks for the passive R60ABD1 demo."""
from datetime import datetime, timedelta
import time
import unittest

from decoder import decode
from demo import Demo, stamp


def packet(control, command, payload):
    data = b"\x53\x59" + bytes([control, command]) + len(payload).to_bytes(2, "big") + payload
    return (data + bytes([sum(data) % 256]) + b"\x54\x43").hex(" ")


def source():
    return dict(started_at="session", epoch=0, console_ok=True, rx_age_s=1,
                status=dict(rx=6, baud=115200, bytes=100, errors=0), frames=[])


def append(state, control, command, payload, historical=False, at=None):
    raw = packet(control, command, payload)
    state["status"]["bytes"] += len(bytes.fromhex(raw))
    state["frames"].append(dict(epoch=state["epoch"], offset_end=state["status"]["bytes"],
                                at=at or stamp(), hex=raw, historical=historical))


class DecodeTests(unittest.TestCase):
    def test_captured_vitals_and_distance(self):
        self.assertEqual(decode("53 59 81 02 00 01 10 40 54 43")["value"], 16)
        self.assertEqual(decode("53 59 85 02 00 01 4C 80 54 43")["value"], 76)
        self.assertEqual(decode("53 59 80 04 00 02 00 2A 5C 54 43")["value"], 42)

    def test_zero_and_outside_handbook_range(self):
        for control in (0x81, 0x85):
            self.assertEqual(decode(packet(control, 2, b"\0"))["quality"], "no_measurement")
        self.assertEqual(decode(packet(0x85, 2, b"\xff"))["quality"], "out_of_range")
        self.assertEqual(decode(packet(0x81, 2, b"\x24"))["quality"], "out_of_range")
        self.assertEqual(decode(packet(0x80, 3, b"\0"))["quality"], "valid")

    def test_corruption_lengths_and_invalid_presence(self):
        good = bytearray.fromhex(packet(0x80, 1, b"\x01"))
        variants = [good[:-1], good + b"\x00"]
        for index in (0, 4, 6, -3, -1):
            corrupt = good.copy()
            corrupt[index] ^= 1
            variants.append(corrupt)
        for value in variants:
            with self.assertRaises(ValueError):
                decode(value.hex())
        with self.assertRaises(ValueError):
            decode(packet(0x80, 1, b"\x02"))
        with self.assertRaises(ValueError):
            decode(packet(0x85, 2, b"\x01\x02"))

    def test_legacy_coordinates_are_not_xyz(self):
        value = decode("53 59 80 05 00 04 00 76 00 5A 05 54 43")
        self.assertEqual(value["value"], [0, 118, 0, 90])
        self.assertEqual(value["quality"], "raw_only")
        self.assertIn("4 字节", value["label"])

    def test_sleep_revision_is_not_assumed(self):
        value = decode(packet(0x84, 2, b"\0"))
        self.assertEqual(value["quality"], "raw_only")
        self.assertNotIn("深睡", value["label"])
        self.assertEqual(value["value"], 0)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.demo = Demo("http://127.0.0.1:18888")
        self.state = source()
        self.demo.ingest(self.state)

    def test_baseline_never_imports_old_module_data(self):
        state = source()
        append(state, 0x85, 2, b"\x50")
        demo = Demo("http://127.0.0.1:18888")
        demo.ingest(state)
        demo.ingest(state)
        self.assertEqual(demo.packets, 0)
        self.assertEqual(demo.fields, {})

    def test_repeated_snapshot_and_stale_without_refreshing_measurement(self):
        old = (datetime.now().astimezone() - timedelta(seconds=20)).isoformat()
        append(self.state, 0x85, 2, b"\x50", at=old)
        self.demo.ingest(self.state)
        self.demo.ingest(self.state)
        self.assertEqual(self.demo.packets, 1)
        self.assertTrue(self.demo.snapshot()["fields"]["heart"]["stale"])

    def test_init_and_presence_off_clear_vitals(self):
        append(self.state, 0x85, 2, b"\x50")
        self.demo.ingest(self.state)
        append(self.state, 0x80, 1, b"\0")
        self.demo.ingest(self.state)
        self.assertNotIn("heart", self.demo.fields)
        self.assertEqual(self.demo.fields["presence"]["value"], 0)
        append(self.state, 5, 1, b"\x0f")
        self.demo.ingest(self.state)
        self.assertEqual(set(self.demo.fields), {"init"})

    def test_restarted_source_and_historical_frames_not_reused(self):
        append(self.state, 0x85, 2, b"\x50")
        self.demo.ingest(self.state)
        self.state["epoch"] = 1
        self.state["frames"] = []
        self.state["status"]["bytes"] = 0
        self.demo.ingest(self.state)
        append(self.state, 0x85, 2, b"\x50", historical=True)
        self.demo.ingest(self.state)
        self.assertEqual(self.demo.fields, {})
        append(self.state, 0x81, 2, b"\x10")
        self.demo.ingest(self.state)
        self.assertEqual(self.demo.fields["breath"]["value"], 16)

    def test_disconnect_and_error_invalidate(self):
        append(self.state, 0x80, 1, b"\x01")
        self.demo.ingest(self.state)
        self.state["console_ok"] = False
        self.demo.ingest(self.state)
        self.assertTrue(self.demo.snapshot()["fields"]["presence"]["stale"])
        self.state["console_ok"] = True
        self.state["status"]["errors"] += 1
        self.demo.ingest(self.state)
        self.assertEqual(self.demo.fields, {})
        self.assertEqual(self.demo.snapshot()["new_uart_errors"], 1)

    def test_poll_timeout_and_activity_do_not_invent_presence(self):
        append(self.state, 0x80, 2, b"\x01")
        self.demo.ingest(self.state)
        self.assertNotIn("presence", self.demo.fields)
        self.demo.last_poll = time.monotonic() - 10
        snapshot = self.demo.snapshot()
        self.assertFalse(snapshot["connected"])
        self.assertTrue(snapshot["fields"]["activity"]["stale"])


if __name__ == "__main__":
    unittest.main()
