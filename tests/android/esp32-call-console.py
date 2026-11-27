"""Local serial bridge for real-esp32-call-e2e.mjs; raw logs stay in build/."""
import argparse
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import threading

import serial
from serial.tools import list_ports


class Console:
    def __init__(self, port, serial_number=None):
        self.port, self.serial_number = port, serial_number
        self.lines = deque(maxlen=1500)
        self.commands = None
        self.lock = threading.Lock()
        self.stop = threading.Event()

    def device(self):
        for item in list_ports.comports():
            if (item.vid, item.pid) != (0x1a86, 0x55d3):
                continue
            if self.serial_number:
                if item.serial_number == self.serial_number:
                    return item
            elif item.device.upper() == self.port.upper():
                return item
        return None

    def submit(self, command):
        with self.lock:
            if self.commands is None:
                return False
            self.commands.put(command)
            return True

    def state(self):
        with self.lock:
            return {'port': self.port, 'connected': self.commands is not None,
                    'lines': list(self.lines)[-180:]}

    def capture(self, log, retry=1):
        while not self.stop.is_set():
            port = None
            try:
                device = self.device()
                if device is not None:
                    port = serial.Serial()
                    port.port, port.baudrate, port.timeout = device.device, 115200, .2
                    port.dtr = port.rts = False
                    port.write_timeout = 1
                    port.open()
                    commands, buffer = queue.Queue(), bytearray()
                    with self.lock:
                        self.port, self.serial_number = device.device, device.serial_number
                        self.commands = commands
                    while not self.stop.is_set():
                        try:
                            command = commands.get_nowait()
                        except queue.Empty:
                            pass
                        else:
                            port.write((command + '\r\n').encode())
                        buffer.extend(port.read(min(port.in_waiting or 1, 4096)))
                        while b'\n' in buffer:
                            raw, _, buffer = buffer.partition(b'\n')
                            text = raw.decode('utf-8', errors='replace').strip('\r')
                            if not text.strip():
                                continue
                            line = datetime.now().isoformat() + ' ' + text
                            log.write(line + '\n')
                            log.flush()
                            with self.lock:
                                self.lines.append(line)
            except serial.SerialException:
                pass  # Windows invalidates the handle on unplug; reopen after enumeration.
            finally:
                with self.lock:
                    self.commands = None  # Never replay an old session's commands on reconnect.
                if port is not None:
                    try:
                        port.close()
                    except OSError:
                        pass
            self.stop.wait(retry)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM13')
    parser.add_argument('--serial-number', help='CH343 USB serial number, also used if Windows changes the COM number')
    parser.add_argument('--http-port', type=int, default=18889)
    args = parser.parse_args()
    console = Console(args.port, args.serial_number)
    Path('build').mkdir(exist_ok=True)

    def reader():
        with Path('build/esp32-real-call-live.log').open('a', encoding='utf-8') as log:
            console.capture(log)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = json.dumps(console.state(), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 128:
                    raise ValueError('Invalid command size')
                command = json.loads(self.rfile.read(size)).get('command')
                if command not in ('i', 'cmd ring', 'cmd answer', 'cmd reject', 'cmd close', 'modem restart'):
                    raise ValueError('Unknown command')
            except (ValueError, AttributeError):
                self.send_error(400)
                return
            if not console.submit(command):
                self.send_error(503, 'ESP32 serial port is offline')
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"queued":true}')

        def log_message(self, *args):
            pass

    worker = threading.Thread(target=reader, daemon=True)
    try:
        with ThreadingHTTPServer(('127.0.0.1', args.http_port), Handler) as server:
            worker.start()
            print(f'ESP32 call console ready http://127.0.0.1:{args.http_port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        console.stop.set()
        if worker.is_alive():
            worker.join(timeout=2)


if __name__ == '__main__':
    main()
