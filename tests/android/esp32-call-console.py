"""Local serial bridge for real-esp32-call-e2e.mjs; raw logs stay in build/."""
import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import threading

import serial
from serial.tools import list_ports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM13')
    parser.add_argument('--http-port', type=int, default=18889)
    args = parser.parse_args()
    device = next((p for p in list_ports.comports() if p.device == args.port), None)
    if device is None or (device.vid, device.pid) != (0x1a86, 0x55d3):
        parser.error('Specified CH343 ESP32 serial port is unavailable')
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = args.port, 115200, .2
    port.dtr = port.rts = False
    port.write_timeout = 1
    port.open()
    commands, lines = queue.Queue(), []
    lock, stop = threading.Lock(), threading.Event()
    Path('build').mkdir(exist_ok=True)

    def reader():
        buffer = bytearray()
        try:
            with Path('build/esp32-real-call-live.log').open('a', encoding='utf-8') as log:
                while not stop.is_set():
                    try:
                        command = commands.get_nowait()
                        port.write((command + '\r\n').encode())
                        print('Console command: ' + command, flush=True)
                    except queue.Empty:
                        pass
                    buffer.extend(port.read(min(port.in_waiting or 1, 4096)))
                    while b'\n' in buffer:
                        raw, _, tail = buffer.partition(b'\n')
                        buffer = bytearray(tail)
                        line = datetime.now().isoformat() + ' ' + raw.decode('utf-8', errors='replace').strip('\r')
                        log.write(line + '\n')
                        log.flush()
                        with lock:
                            lines.append(line)
                            if len(lines) > 1500:
                                del lines[:500]
        finally:
            port.close()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                data = json.dumps({'lines': lines[-180:], 'port': args.port}, ensure_ascii=False).encode()
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
                if command not in ('i', 'cmd ring', 'cmd answer', 'cmd reject', 'cmd close'):
                    raise ValueError('Unknown command')
            except (ValueError, AttributeError):
                self.send_error(400)
                return
            commands.put(command)
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
        stop.set()
        if worker.is_alive():
            worker.join(timeout=2)
        port.close()


if __name__ == '__main__':
    main()
