"""Check saved-log following without opening or resetting physical serial ports."""
import importlib.util
import json
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

    def test_bounded_screen_history_preserves_complete_file(self):
        self.path.write_text("".join(f"line {number}\n" for number in range(5000)), encoding="utf-8")
        self.reader.tick()
        snapshot = self.reader.snapshot()
        self.assertEqual(4000, len(snapshot["lines"]))
        self.assertEqual("line 1000", snapshot["lines"][0]["text"])
        self.assertEqual(5000, len(self.path.read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
