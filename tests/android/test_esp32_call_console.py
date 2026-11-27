"""Hotplug regression: the physical relay must not replay queued call commands."""
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('bridge', Path(__file__).with_name('esp32-call-console.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class HotplugTest(unittest.TestCase):
    def test_unplug_then_new_com(self):
        def ch343(port, serial_number):
            return SimpleNamespace(device=port, vid=0x1a86, pid=0x55d3, serial_number=serial_number)

        console = bridge.Console('COM13')
        first, other, second = ch343('COM13', 'ours'), ch343('COM13', 'other'), ch343('COM16', 'ours')
        writes, opened = [], []

        def disconnect():
            self.assertTrue(console.submit('cmd ring'))
            raise bridge.serial.SerialException('USB removed')

        def offline():
            self.assertFalse(console.state()['connected'])
            self.assertFalse(console.submit('cmd answer'))
            return [other]

        def finish():
            console.stop.set()
            return b''

        phases = iter([lambda: [], lambda: [first], offline, lambda: [other, second]])
        packets = iter([iter([b'before\r\npartial', disconnect]), iter([b'after\r\n', finish])])

        class Serial:
            in_waiting = 64

            def open(self):
                opened.append(self.port)
                self.rx = next(packets)

            def read(self, _):
                result = next(self.rx)
                return result() if callable(result) else result

            def write(self, data):
                writes.append(data)

            def close(self):
                pass

        log = io.StringIO()
        with patch.object(bridge.list_ports, 'comports', side_effect=lambda: next(phases)()), \
                patch.object(bridge.serial, 'Serial', Serial):
            console.capture(log, retry=0)
        self.assertEqual(opened, ['COM13', 'COM16'])
        self.assertEqual(writes, [])
        self.assertEqual(log.getvalue().splitlines(), console.state()['lines'])
        self.assertEqual([line.split(' ', 1)[1] for line in console.state()['lines']], ['before', 'after'])


if __name__ == '__main__':
    unittest.main()
