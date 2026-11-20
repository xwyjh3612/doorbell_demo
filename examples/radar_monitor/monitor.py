"""Read-only radar dashboard for the GPIO demo and optional voice/radar firmware."""
import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

import serial
from serial.tools import list_ports
from telemetry import Telemetry


class Monitor:
    def __init__(self, port, output):
        self.port = port
        self.output = output
        self.output.mkdir(parents=True, exist_ok=True)
        self.data = Telemetry()
        self.data.port = port
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.last_saved_frames_epoch = -1
        self.last_saved_frame_end = -1

    def state(self):
        with self.lock:
            state = self.data.snapshot()
        state["log_dir"] = str(self.output.resolve())
        return state

    def connection(self, value, note):
        with self.lock:
            self.data.connection = value
            self.data.connection_note = note

    def save_state(self):
        temp = self.output / "state.tmp"
        temp.write_text(json.dumps(self.state(), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.output / "state.json")

    def serial_loop(self):
        # Reconnect only to the same known board; never claim another serial port.
        expected_serial = None
        while not self.stop.is_set():
            port = None
            try:
                device = next((p for p in list_ports.comports()
                               if p.device.casefold() == self.port.casefold()), None)
                if device is None or (device.vid, device.pid) != (0x1A86, 0x55D3):
                    raise OSError("未找到指定CH343串口，等待设备连接")
                if expected_serial is not None and device.serial_number != expected_serial:
                    raise OSError("串口设备身份变化，未连接")
                expected_serial = device.serial_number
                port = serial.Serial()
                port.port, port.baudrate, port.timeout = self.port, 115200, 0.2
                port.dtr = port.rts = False
                port.write_timeout = 1
                port.open()
                self.connection("identifying", "已打开串口，正在确认雷达接收固件")
                buffer = bytearray()
                identified = False
                identify_deadline = time.monotonic() + 10
                next_save = 0
                with (self.output / "console.bin").open("ab") as rawlog, \
                        (self.output / "console.log").open("a", encoding="utf-8") as textlog, \
                        (self.output / "frames.jsonl").open("a", encoding="utf-8") as framefile:
                    while not self.stop.is_set():
                        chunk = port.read(min(port.in_waiting or 1, 4096))
                        if chunk:
                            rawlog.write(chunk)
                            rawlog.flush()
                            buffer.extend(chunk)
                            while b"\n" in buffer:
                                line, _, tail = buffer.partition(b"\n")
                                buffer = bytearray(tail)
                                text = line.decode("utf-8", errors="replace").strip("\r")
                                textlog.write(f"{datetime.now().astimezone().isoformat()} {text}\n")
                                textlog.flush()
                                with self.lock:
                                    self.data.feed(text)
                                    if "RADAR_GPIO5: STATUS rx=" in text or "RADAR_GPIO5: READY console=UART0" in text:
                                        identified = True
                                        self.data.connection = "connected"
                                        self.data.connection_note = "雷达接收固件已确认，持续记录中"
                                    new_frames = [f for f in self.data.frames
                                                  if f["epoch"] > self.last_saved_frames_epoch or
                                                  (f["epoch"] == self.last_saved_frames_epoch and
                                                   f["offset_end"] > self.last_saved_frame_end)]
                                    for frame in reversed(new_frames):
                                        framefile.write(json.dumps(frame, ensure_ascii=False) + "\n")
                                        self.last_saved_frames_epoch = frame["epoch"]
                                        self.last_saved_frame_end = frame["offset_end"]
                                    framefile.flush()
                            if len(buffer) > 16384:
                                buffer.clear()
                        now = time.monotonic()
                        if not identified and now > identify_deadline:
                            raise OSError("没有识别到雷达接收固件；没有发送控制台命令")
                        # Firmware emits STATUS itself. Passive collection avoids
                        # repeated history hex dumps and extra work during calls.
                        if now >= next_save:
                            self.save_state()
                            next_save = now + 2
                self.connection("stopped", "采集已停止")
            except (OSError, serial.SerialException) as error:
                self.connection("disconnected", str(error))
                self.save_state()
            finally:
                if port is not None:
                    port.close()
            self.stop.wait(2)
        self.connection("stopped", "采集已停止")
        self.save_state()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM13")
    parser.add_argument("--http-port", type=int, default=18888)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    monitor = Monitor(args.port, args.output)
    page = Path(__file__).with_name("index.html")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/state":
                body = json.dumps(monitor.state(), ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif path == "/api/export":
                body = json.dumps(monitor.state(), ensure_ascii=False, indent=2).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif path in ("/", "/index.html") and page.exists():
                body, content_type = page.read_bytes(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if path == "/api/export":
                self.send_header("Content-Disposition", 'attachment; filename="radar-state.json"')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler)
    thread = threading.Thread(target=monitor.serial_loop, daemon=True)
    thread.start()
    print(f"Radar monitor: http://127.0.0.1:{args.http_port} ; logs: {args.output.resolve()}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop.set()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
