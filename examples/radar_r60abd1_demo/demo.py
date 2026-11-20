"""Local R60ABD1 dashboard, consuming the existing radar monitor over HTTP."""
import argparse
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from decoder import decode


def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Demo:
    def __init__(self, source):
        self.source = source
        self.started_at = stamp()
        self.started_mono = time.monotonic()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.session = None
        self.highwater = -1
        self.fields = {}
        self.frames = deque(maxlen=80)
        self.samples = deque(maxlen=600)
        self.connected = False
        self.note = "正在连接现有采集服务"
        self.status = None
        self.rx_age = None
        self.last_poll = None
        self.packets = self.decoded = self.rejected = self.unknown = 0
        self.baseline_bytes = self.baseline_errors = None
        self.previous_errors = None
        self.resets = 0
        self.summary_valid = None

    def ingest(self, source):
        self.last_poll = time.monotonic()
        self.connected = bool(source.get("console_ok"))
        self.note = "正在接收" if self.connected else "采集服务在线，等待 ESP32 数据"
        self.status = source.get("status")
        self.rx_age = source.get("rx_age_s")
        status = self.status or {}
        session = (source.get("started_at"), source.get("epoch"),
                   status.get("rx"), status.get("baud"))
        if not status:
            return
        errors = status.get("errors", 0)
        if session != self.session:
            self.fields.clear()
            self.samples.clear()
            self.resets += int(self.session is not None)
            self.session = session
            self.baseline_bytes = status.get("bytes", 0)
            self.baseline_errors = self.previous_errors = errors
            self.summary_valid = None
            # Do not import earlier radar/module data, even if it was once live.
            self.highwater = max((f["offset_end"] for f in source.get("frames", [])
                                  if f.get("epoch") == source.get("epoch")), default=-1)
            return
        if errors != self.previous_errors:
            self.fields.clear()
            self.previous_errors = errors
        for frame in sorted(source.get("frames", []), key=lambda f: f["offset_end"]):
            if frame.get("epoch") != source.get("epoch") or frame["offset_end"] <= self.highwater:
                continue
            self.highwater = frame["offset_end"]
            if frame.get("historical"):
                continue
            try:
                parsed = decode(frame["hex"])
            except (ValueError, KeyError):
                self.rejected += 1
                continue
            self.packets += 1
            row = dict(at=frame["at"], hex=frame["hex"], offset_end=frame["offset_end"],
                       name=parsed["name"] if parsed else "unknown",
                       label=parsed["label"] if parsed else "未解析的有效报文")
            self.frames.appendleft(row)
            if parsed is None:
                self.unknown += 1
                continue
            self.decoded += 1
            name = parsed["name"]
            if name == "init":
                self.fields.clear()
                self.samples.clear()
                self.resets += 1
            elif name == "presence" and parsed["value"] == 0:
                for key in ("breath", "heart", "distance", "coordinates", "breath_wave", "heart_wave"):
                    self.fields.pop(key, None)
            self.fields[name] = dict(parsed, at=frame["at"])
            if name in ("breath", "heart", "motion", "distance"):
                self.samples.append(dict(name=name, at=frame["at"], value=parsed["value"],
                                         quality=parsed["quality"]))
        summary = source.get("summary")
        if summary and summary.get("valid") != self.summary_valid:
            self.summary_valid = summary.get("valid")
            # Receive-only mode uses firmware summaries, not raw frames. The
            # timestamp is when this snapshot was printed, not measurement time.
            mapping = {"activity": ("activity", ""), "breath": ("breath", "次/分"),
                       "heart": ("heart", "次/分"), "distance_cm": ("distance", "cm"),
                       "presence": ("presence", "")}
            for key, (name, unit) in mapping.items():
                value = summary.get(key, -1)
                if value < 0:
                    self.fields.pop(name, None)
                    continue
                label = {0: "无活动目标", 1: "静止", 2: "活跃"}.get(value, str(value)) if name == "activity" else str(value)
                if name == "presence":
                    label = "有人" if value else "无人"
                self.fields[name] = dict(name=name, value=value, label=label, unit=unit,
                                         quality="snapshot", at=summary["at"], source="firmware_summary")
            self.note = "正在接收固件摘要（非原始报文，时间为摘要打印时间）"

    def snapshot(self):
        now = time.monotonic()
        live = self.connected and self.last_poll is not None and now - self.last_poll < 5
        fields = {}
        for name, field in self.fields.items():
            age = max(0, (datetime.now().astimezone() - datetime.fromisoformat(field["at"])).total_seconds())
            periodic = name in ("breath", "heart", "motion", "distance", "coordinates",
                                "breath_wave", "heart_wave")
            stale = (not live or age > 12) if field.get("source") == "firmware_summary" else (
                not live or self.rx_age is None or self.rx_age > 12 or (periodic and age > 12))
            fields[name] = dict(field, age_s=round(age, 1), stale=stale)
        status = self.status or {}
        note = self.note if live or not self.connected else "采集数据暂未更新"
        if live and not self.summary_valid and (self.rx_age is None or self.rx_age > 12):
            note = "采集连接正常，雷达暂未更新"
        # Only radar fields leave this process; never expose MQTT/SDP console logs.
        return dict(model="R60ABD1.1 / V0220 (照片)", started_at=self.started_at,
                    elapsed_s=round(now - self.started_mono), source=self.source,
                    connected=live, note=note,
                    uart=status, rx_age_s=self.rx_age, packets=self.packets,
                    decoded=self.decoded, rejected=self.rejected, unknown=self.unknown,
                    new_bytes=max(0, status.get("bytes", 0) - (self.baseline_bytes or 0)),
                    new_uart_errors=max(0, status.get("errors", 0) - (self.baseline_errors or 0)),
                    resets=self.resets, fields=fields, frames=list(self.frames), samples=list(self.samples))

    def poll(self):
        while not self.stop.is_set():
            try:
                with urlopen(self.source + "/api/state", timeout=2) as response:
                    source = json.load(response)
                with self.lock:
                    self.ingest(source)
            except (OSError, ValueError, KeyError, TypeError):
                with self.lock:
                    self.connected = False
                    self.note = "采集服务暂不可用，请检查 18888 服务和 USB"
            self.stop.wait(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="http://127.0.0.1:18888")
    parser.add_argument("--http-port", type=int, default=18890)
    args = parser.parse_args()
    parsed = urlsplit(args.source)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path not in ("", "/"):
        parser.error("source must be a local http://127.0.0.1 radar monitor")
    demo = Demo(args.source.rstrip("/"))
    page = Path(__file__).with_name("index.html")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ("/api/state", "/api/export"):
                with demo.lock:
                    state = demo.snapshot()
                body = json.dumps(state, ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif path in ("/", "/index.html"):
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
                self.send_header("Content-Disposition", 'attachment; filename="r60abd1-demo.json"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler)
    thread = threading.Thread(target=demo.poll, daemon=True)
    thread.start()
    print(f"R60ABD1 demo: http://127.0.0.1:{args.http_port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        demo.stop.set()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
