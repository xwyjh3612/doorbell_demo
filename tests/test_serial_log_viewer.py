"""Check saved-log following without opening or resetting physical serial ports."""
import importlib.util
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "ttl_viewer", Path(__file__).resolve().parents[1] / "examples/serial_log_viewer/server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LogFollowingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ttl-viewer-test-")
        self.root = Path(self.temp.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.path = self.make_log("radar-monitor-first", "初始记录\n")
        self.point_at(self.path)
        self.reader = module.LogReader(self.root)

    def tearDown(self):
        self.reader.close()
        self.temp.cleanup()

    def make_log(self, name, text):
        directory = self.build / name
        directory.mkdir()
        path = directory / "console.log"
        path.write_text(text, encoding="utf-8")
        return path

    def point_at(self, path):
        (self.build / "radar-monitor-service.json").write_text(
            json.dumps({"output": str(path.parent)}), encoding="utf-8-sig")

    def test_incremental_utf8_and_original_bytes_untouched(self):
        self.reader.tick()
        before = self.reader.snapshot()
        text = "\x1b[31m来电已接听\x1b[0m\n".encode()
        with self.path.open("ab") as output:
            output.write(text[:7])  # Split in the middle of a Chinese character.
        self.reader.tick()
        self.assertEqual([], self.reader.snapshot(before["last_id"], before["epoch"])["lines"])
        with self.path.open("ab") as output:
            output.write(text[7:])
        self.reader.tick()
        update = self.reader.snapshot(before["last_id"], before["epoch"])
        self.assertFalse(update["reset"])
        self.assertEqual("来电已接听", update["lines"][0]["text"])
        self.assertTrue(self.path.read_bytes().endswith(text))

    def test_new_collector_and_truncation_reset_history(self):
        self.reader.tick()
        previous = self.reader.snapshot()
        second = self.make_log("radar-monitor-second", "恢复后记录\n")
        self.point_at(second)
        self.reader.tick()
        update = self.reader.snapshot(previous["last_id"], previous["epoch"])
        self.assertTrue(update["reset"])
        self.assertEqual(["恢复后记录"], [line["text"] for line in update["lines"]])
        second.write_text("新\n", encoding="utf-8")
        self.reader.tick()
        self.assertEqual("新", self.reader.snapshot()["lines"][0]["text"])

    def test_history_choice_does_not_follow_metadata(self):
        second = self.make_log("radar-monitor-second", "第二份\n")
        self.reader.select("radar-monitor-first/console.log")
        self.point_at(second)
        self.reader.tick()
        self.assertEqual("初始记录", self.reader.snapshot()["lines"][0]["text"])
        with self.assertRaises(ValueError):
            self.reader.select("../outside.log")

    def test_live_uses_call_collector_instead_of_stale_radar_metadata(self):
        old_stamp = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
        os.utime(self.path, (old_stamp, old_stamp))
        call_log = self.build / "esp32-real-call-live.log"
        call_log.write_text("新串口通话日志\n", encoding="utf-8")
        self.reader.tick()
        self.assertEqual(str(call_log), self.reader.snapshot()["path"])
        self.assertEqual("新串口通话日志", self.reader.snapshot()["lines"][0]["text"])
        self.reader.select("radar-monitor-first/console.log")
        self.reader.tick()
        self.assertEqual("初始记录", self.reader.snapshot()["lines"][0]["text"])

    def test_bounded_screen_history_preserves_complete_file(self):
        self.path.write_text("".join(f"line {number}\n" for number in range(5000)), encoding="utf-8")
        self.reader.tick()
        snapshot = self.reader.snapshot()
        self.assertEqual(4000, len(snapshot["lines"]))
        self.assertEqual("line 1000", snapshot["lines"][0]["text"])
        self.assertEqual(5000, len(self.path.read_text().splitlines()))


class CallHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="voice-call-viewer-")
        self.root = Path(self.temp.name)
        self.batch = self.root / "build" / "formal-40"
        self.batch.mkdir(parents=True)
        self.history = module.CallHistory(self.root)
        self.state = {"startedAt": "2026-11-26T07:00:00Z", "updatedAt": datetime.now(timezone.utc).isoformat(),
                      "targetSecondsPerRound": 1800, "requestedConnectedRounds": 40, "phase": "calling", "attempts": []}

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        (self.batch / "state.json").write_text(json.dumps(self.state), encoding="utf-8")

    def result(self, number, data):
        directory = self.batch / f"attempt-{number}"
        directory.mkdir(exist_ok=True)
        (directory / "results.json").write_text(json.dumps(data), encoding="utf-8")
        return directory

    def test_counted_failures_exclusions_and_utc_local_duration(self):
        self.state["attempts"] = [
            {"attempt": 1, "connectedAt": "2026-11-26T15:00:00", "completedAt": "2026-11-26T07:30:00Z", "passed": True},
            {"attempt": 2, "connectedAt": "2026-11-26T15:31:00", "completedAt": "2026-11-26T07:33:00Z", "passed": False,
             "error": "AFE feed buffer overflow during connected call"},
            {"attempt": 3, "connectedAt": "2026-11-26T15:34:00", "passed": False,
             "failureClassification": "test-server-interruption"},
            {"attempt": 4, "connectedAt": None, "passed": False, "error": "Missing native state 设备来电"},
            {"attempt": 5, "connectedAt": "2026-11-26T15:35:00", "passed": False,
             "failureClassification": "test-supervisor-interruption"},
        ]
        self.result(1, {"startedAt": "2026-11-26T06:59:55Z", "connectedAt": "2026-11-26T15:00:00"})
        self.save()
        snapshot = self.history.snapshot()
        self.assertEqual({"completed": 2, "passed": 1, "failed": 1, "excluded": 2, "setup_failed": 1}, snapshot["summary"])
        by_number = {r["attempt"]: r for r in snapshot["records"]}
        self.assertEqual(1800, by_number[1]["duration_seconds"])
        self.assertEqual("2026-11-26T06:59:55Z", by_number[1]["started_at"])
        self.assertEqual(2, by_number[2]["round"])
        self.assertIn("底层原因尚未确认", by_number[2]["reason"])
        self.assertEqual("setup-failed", by_number[4]["status"])
        self.assertIsNone(by_number[3]["round"])

    def test_user_power_annotation_preserves_error_and_recounts_live_round(self):
        connected = "2026-11-26T17:11:16.776701"
        self.state["attempts"] = [
            {"attempt": 1, "connectedAt": connected, "passed": False,
             "error": "Bidirectional audio stopped for over 12 seconds"},
            {"attempt": 2, "connectedAt": "2026-11-26T17:49:36", "passed": True},
        ]
        self.state["active"] = {"attempt": 3, "round": 3, "connectedAt": "2026-11-26T18:20:00"}
        annotations = {"attempts": [{"attempt": 1, "connectedAt": connected,
            "failureClassification": "test-user-power-interruption",
            "classificationEvidence": {"source": "user-report", "action": "UPS unplugged",
                                       "causalLinkConfirmed": False}}]}
        annotation_file = self.batch / "operator-annotations.json"
        annotation_file.write_text(json.dumps(annotations), encoding="utf-8")
        self.save()
        original_bytes = (self.batch / "state.json").read_bytes()
        snapshot = self.history.snapshot()
        self.assertEqual({"completed": 1, "passed": 1, "failed": 0, "excluded": 1, "setup_failed": 0}, snapshot["summary"])
        excluded = next(record for record in snapshot["records"] if record["attempt"] == 1)
        self.assertEqual("excluded", excluded["status"])
        self.assertIn("UPS", excluded["reason"])
        self.assertEqual("Bidirectional audio stopped for over 12 seconds", excluded["error"])
        self.assertEqual(2, snapshot["active"]["round"])
        self.assertEqual(original_bytes, (self.batch / "state.json").read_bytes())
        annotations["attempts"][0]["connectedAt"] = "different call"
        annotation_file.write_text(json.dumps(annotations), encoding="utf-8")
        self.assertEqual(1, self.history.snapshot()["summary"]["failed"])

    def test_live_call_and_stale_snapshot_stop_at_last_audio(self):
        now = datetime.now(timezone.utc)
        connected = (now - timedelta(minutes=10)).astimezone(module.TEST_TIMEZONE).replace(tzinfo=None).isoformat()
        audio = (now - timedelta(seconds=2)).astimezone(module.TEST_TIMEZONE).replace(tzinfo=None).isoformat()
        self.state["active"] = {"attempt": 1, "round": 1, "connectedAt": connected, "startedAt": connected}
        directory = self.result(1, {"connectedAt": connected, "audioSamples": [{"at": audio, "sentBytes": 100, "receivedBytes": 100}]})
        (directory / "operator-commands.jsonl").write_text(
            json.dumps({"at": "2026-11-26T07:00:00Z", "command": "cmd ring"}) + "\n", encoding="utf-8")
        self.save()
        active = self.history.snapshot()["active"]
        self.assertEqual("connected", active["status"])
        self.assertAlmostEqual(600, active["duration_seconds"], delta=2)
        self.assertEqual("设备发起呼叫", active["start_kind"])
        self.assertEqual("2026-11-26T07:00:00Z", active["started_at"])
        self.state["updatedAt"] = (now - timedelta(minutes=5)).isoformat()
        self.save()
        active = self.history.snapshot()["active"]
        self.assertEqual("stale", active["status"])
        self.assertAlmostEqual(598, active["duration_seconds"], delta=1)
        self.assertIsNone(active["ended_at"])

    def test_partial_write_keeps_snapshot_and_external_batch_is_rejected(self):
        self.save()
        self.history.snapshot()
        (self.batch / "state.json").write_text('{"attempts":', encoding="utf-8")
        self.assertEqual("formal-40", self.history.snapshot()["batch"])
        with self.assertRaises(ValueError):
            self.history.snapshot("../../outside")
        self.assertEqual({}, self.history.read_json(self.root / "outside.json"))

    def test_copied_cohort_does_not_attach_another_calls_times(self):
        self.state["attempts"] = [{"attempt": 1, "connectedAt": "2026-11-26T15:00:00", "passed": True}]
        self.result(1, {"connectedAt": "2026-11-25T15:00:00", "startedAt": "wrong-call"})
        self.save()
        self.assertIsNone(self.history.snapshot()["records"][0]["started_at"])

    def test_watchdog_is_not_mislabeled_as_modem_power_loss(self):
        reason = module.CallHistory.reason({"failureEvent": "Guru Meditation Error: Interrupt wdt timeout on CPU1"}, {}, "failed")
        self.assertIn("中断看门狗超时", reason)
        self.assertNotIn("模组重新启动", reason)

    def test_afe_warning_followed_by_audio_and_test_hangup_is_explicit(self):
        self.state["attempts"] = [{"attempt": 1, "connectedAt": "2026-11-26T15:00:00", "passed": False,
                                  "error": "AFE feed buffer overflow during connected call"}]
        directory = self.result(1, {"connectedAt": "2026-11-26T15:00:00",
                                   "firstAfeAlert": "2026-11-26T15:20:00 AFE: Ringbuffer of AFE(FEED) is full",
                                   "audioSamples": [{"at": "2026-11-26T15:20:07", "sentBytes": 100, "receivedBytes": 100}]})
        (directory / "operator-commands.jsonl").write_text(
            json.dumps({"at": "2026-11-26T07:00:00Z", "command": "cmd ring"}) + "\n" +
            json.dumps({"at": "2026-11-26T07:20:08Z", "command": "cmd close"}) + "\n", encoding="utf-8")
        self.save()
        record = self.history.snapshot()["records"][0]
        self.assertEqual(7, record["audio_continued_after_afe_seconds"])
        self.assertTrue(record["test_stopped_on_afe"])
        self.assertIn("测试程序主动挂断", record["reason"])
        self.assertEqual(1, self.history.snapshot()["summary"]["failed"])


if __name__ == "__main__":
    unittest.main()
