"""Local TTL log viewer. Follow the existing collector without claiming its port."""
import argparse
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LOG_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")


class LogReader:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.build = self.root / "build"
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.lines = deque(maxlen=4000)
        self.sequence = 0
        self.epoch = 0
        self.path = None
        self.file = None
        self.pending = b""
        self.selection = "live"
        self.note = "正在寻找串口采集日志"

    def sources(self):
        paths = list(self.build.glob("radar-monitor*/console.log"))
        extra = self.build / "esp32-real-call-live.log"
        if extra.exists():
            paths.append(extra)
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return {p.relative_to(self.build).as_posix(): p for p in paths}

    def selected_path(self):
        if self.selection != "live":
            return self.sources().get(self.selection)
        metadata = self.build / "radar-monitor-service.json"
        try:
            output = Path(json.loads(metadata.read_text(encoding="utf-8-sig"))["output"])
            path = (output / "console.log").resolve()
            if path.is_relative_to(self.build.resolve()) and path.exists():
                return path
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def select(self, source):
        with self.lock:
            if source != "live" and source not in self.sources():
                raise ValueError("未找到该日志")
            self.selection = source
            self.close()
            self.path = None
            self.lines.clear()
            self.pending = b""
            self.epoch += 1

    def close(self):
        if self.file:
            self.file.close()
            self.file = None

    def open_path(self, path):
        self.close()
        self.path = path
        self.lines.clear()
        self.pending = b""
        self.epoch += 1
        self.file = path.open("rb")
        # Start with recent history; full records remain available on disk.
        size = path.stat().st_size
        if size > 1024 * 1024:
            self.file.seek(size - 1024 * 1024)
            self.file.readline()  # Drop the partial first UTF-8 line.

    def tick(self):
        with self.lock:
            path = self.selected_path()
            if path is None:
                self.note = "等待串口采集日志；插好设备后会自动更新"
                return
            if path != self.path or self.file is None:
                self.open_path(path)
            elif path.stat().st_size < self.file.tell():
                self.open_path(path)
            chunk = self.file.read(512 * 1024)
            self.pending += chunk
            parts = self.pending.split(b"\n")
            self.pending = parts.pop()
            for raw in parts:
                text = ANSI.sub("", raw.decode("utf-8", "replace").rstrip("\r"))
                # The serial collector timestamps empty UART lines too. They
                # should not scroll the page or evict useful screen history.
                content = text.strip()
                if not content or LOG_TIMESTAMP.fullmatch(content):
                    continue
                self.sequence += 1
                self.lines.append({"id": self.sequence, "text": text})
            self.note = "正在跟随实时日志" if self.selection == "live" else "正在查看历史日志"

    def snapshot(self, after=0, epoch=-1):
        with self.lock:
            reset = epoch != self.epoch or after > self.sequence or (self.lines and after < self.lines[0]["id"] - 1)
            selected = list(self.lines) if reset else [line for line in self.lines if line["id"] > after]
            stat = self.path.stat() if self.path and self.path.exists() else None
            return {"epoch": self.epoch, "last_id": self.sequence, "reset": bool(reset),
                    "lines": selected, "selection": self.selection, "note": self.note,
                    "path": str(self.path) if self.path else None,
                    "bytes": stat.st_size if stat else 0,
                    "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds") if stat else None}

    def loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except (OSError, ValueError) as error:
                with self.lock:
                    self.note = "等待日志恢复：" + str(error)
                    self.close()
            self.stop.wait(.25)
        with self.lock:
            self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http-port", type=int, default=18891)
    args = parser.parse_args()
    reader = LogReader()
    page = Path(__file__).with_name("index.html")

    class Handler(BaseHTTPRequestHandler):
        def local_request(self):
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{args.http_port}", f"localhost:{args.http_port}"}
            origin = self.headers.get("Origin")
            return host in allowed and (not origin or origin in {"http://" + h for h in allowed})

        def respond(self, body, content_type="application/json; charset=utf-8"):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.local_request():
                self.send_error(403)
                return
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/":
                self.respond(page.read_bytes(), "text/html; charset=utf-8")
            elif parsed.path == "/api/state":
                try:
                    self.respond(reader.snapshot(int(query.get("after", [0])[0]), int(query.get("epoch", [-1])[0])))
                except ValueError:
                    self.send_error(400)
            elif parsed.path == "/api/sources":
                with reader.lock:
                    self.respond({"sources": list(reader.sources())})
            elif parsed.path == "/api/download":
                with reader.lock:
                    path = reader.path
                    size = path.stat().st_size if path and path.exists() else 0
                if not path:
                    self.send_error(404)
                    return
                with path.open("rb") as source:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="ttl-console.log"')
                    self.send_header("Content-Length", str(size))
                    self.end_headers()
                    remaining = size
                    while remaining:
                        chunk = source.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            else:
                self.send_error(404)

        def do_POST(self):
            if not self.local_request() or urlsplit(self.path).path != "/api/source":
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length < 4096:
                    raise ValueError("Invalid request")
                reader.select(json.loads(self.rfile.read(length))["source"])
                self.respond({"ok": True})
            except (ValueError, KeyError, TypeError):
                self.send_error(400)

        def log_message(self, *_args):
            pass

    worker = threading.Thread(target=reader.loop, daemon=True)
    with ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler) as server:
        worker.start()
        print(f"TTL viewer: http://127.0.0.1:{args.http_port}", flush=True)
        try:
            server.serve_forever(poll_interval=.5)
        except KeyboardInterrupt:
            pass
        finally:
            reader.stop.set()
            worker.join(timeout=3)


if __name__ == "__main__":
    main()
