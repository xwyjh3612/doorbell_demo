"""Parse diagnostic console snapshots, never guess presence from raw byte counts."""
from collections import deque
from datetime import datetime
import re
import time

STAMP = re.compile(r"\b[IWED] \((\d+)\)")
STATUS = re.compile(r"RADAR_GPIO5: STATUS rx=(\d+) baud=(\d+) bytes=(\d+) errors=(\d+) header5359=(\d+) level=(\d+)")
HISTORY = re.compile(r"RADAR_GPIO5: HISTORY rx=(\d+) baud=(\d+) saved=(\d+) total=(\d+) last_ms=(\d+)")
HEX = re.compile(r"RADAR_GPIO5: ((?:[0-9a-fA-F]{2} ){0,127}[0-9a-fA-F]{2})\s*$")


def clock():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def frames_in(data):
    """Find length/tail/checksum-valid 53 59 frames, including after bad headers."""
    cursor = 0
    while cursor < len(data):
        start = data.find(b"\x53\x59", cursor)
        if start < 0 or start + 6 > len(data):
            return
        length = int.from_bytes(data[start + 4:start + 6], "big")
        end = start + length + 9
        if length <= 503 and end <= len(data):
            packet = data[start:end]
            if packet[-2:] == b"\x54\x43" and sum(packet[:-3]) % 256 == packet[-3]:
                yield start, end, packet
                cursor = end
                continue
        cursor = start + 1


class Telemetry:
    def __init__(self):
        self.started_at = clock()
        self.started_mono = time.monotonic()
        self.status = None
        self.uptime_ms = 0
        self.last_status_mono = None
        self.last_console_at = None
        self.last_rx_ms = None
        self.last_snapshot_total = None
        self.snapshot_count = 0
        self.valid_frames = 0
        self.new_bytes = 0
        self.breaks = 0
        self.epoch = 0
        self.presence = None
        self.presence_observed_at = None
        self.frames = deque(maxlen=120)
        self.logs = deque(maxlen=200)
        self.byte_samples = deque(maxlen=360)
        self.pending = None
        self.frame_highwater = -1
        self.config = None
        self.previous_total = None
        self.previous_uptime = None
        self.connection = "connecting"
        self.connection_note = "正在连接串口"
        self.port = None

    def _context(self, rx, baud, total, uptime):
        if (self.config is not None and
                ((rx, baud) != self.config or total < self.previous_total or
                 (self.previous_uptime is not None and uptime < self.previous_uptime))):
            self.epoch += 1
            self.frame_highwater = -1
            self.last_snapshot_total = None
            self.last_rx_ms = None
            self.presence = None
            self.presence_observed_at = None
            self.pending = None
        elif self.previous_total is not None:
            self.new_bytes += max(0, total - self.previous_total)
        self.config = (rx, baud)
        self.previous_total = total
        self.previous_uptime = uptime

    def feed(self, line):
        stamp = STAMP.search(line)
        uptime = int(stamp[1]) if stamp else self.uptime_ms
        # Console timestamps can interleave between tasks; restart detection uses
        # sequential STATUS/HISTORY records from the sole radar reader task.
        self.uptime_ms = max(self.uptime_ms, uptime)
        self.last_console_at = clock()
        self.logs.append({"at": self.last_console_at, "line": line})
        match = STATUS.search(line)
        if match:
            rx, baud, total, errors, headers, level = map(int, match.groups())
            if self.previous_uptime is not None and uptime < self.previous_uptime:
                self.uptime_ms = uptime
            self._context(rx, baud, total, uptime)
            self.status = dict(rx=rx, baud=baud, bytes=total, errors=errors,
                               headers=headers, level=level)
            # Integrated firmware explicitly invalidates state on UART errors.
            # Keep demo support: these trailing fields do not exist there.
            reported = re.search(r"\bpresence=(-?\d+)\b", line)
            if reported and int(reported[1]) == -1:
                self.presence = None
                self.presence_observed_at = None
            breaks = re.search(r"\bbreaks=(\d+)\b", line)
            if breaks:
                self.breaks = int(breaks[1])
            self.last_status_mono = time.monotonic()
            self.byte_samples.append({"at": clock(), "bytes": total, "epoch": self.epoch})
            return
        match = HISTORY.search(line)
        if match:
            rx, baud, saved, total, last_ms = map(int, match.groups())
            if saved > 512 or saved > total:
                self.pending = None
                return
            if self.previous_uptime is not None and uptime < self.previous_uptime:
                self.uptime_ms = uptime
            self._context(rx, baud, total, uptime)
            self.pending = dict(rx=rx, baud=baud, saved=saved, total=total,
                                last_ms=last_ms, data=bytearray(), at=clock(),
                                historical=self.last_snapshot_total is None)
            if not saved:
                self._finish_history()
            return
        match = HEX.search(line)
        if match and self.pending is not None:
            self.pending["data"].extend(bytes.fromhex(match[1]))
            if len(self.pending["data"]) == self.pending["saved"]:
                self._finish_history()
            elif len(self.pending["data"]) > self.pending["saved"]:
                self.pending = None
            return
        if "RADAR_GPIO5: UART BREAK" in line:
            self.breaks += 1
        # A snapshot consists solely of the immediately following HEX lines.
        if "RADAR_GPIO5:" in line:
            self.pending = None

    def _finish_history(self):
        block = self.pending
        self.pending = None
        self.snapshot_count += 1
        self.last_snapshot_total = block["total"]
        self.last_rx_ms = block["last_ms"] if block["total"] else None
        base = block["total"] - block["saved"]
        for start, end, packet in frames_in(bytes(block["data"])):
            offset_end = base + end
            if offset_end <= self.frame_highwater:
                continue
            self.frame_highwater = offset_end
            self.valid_frames += 1
            control, command, payload = packet[2], packet[3], packet[6:-3]
            kind, label = "other", "其他有效报文"
            if (control, command, payload) == (5, 1, b"\x0f"):
                kind, label = "init", "初始化完成"
                # Earlier presence may predate the radar's restart.
                self.presence = None
                self.presence_observed_at = None
            elif control == 0x80 and command == 1 and payload in (b"\x00", b"\x01"):
                kind = "presence"
                self.presence = payload == b"\x01"
                label = "有人" if self.presence else "无人"
                self.presence_observed_at = block["at"]
            elif control == 0x80 and command == 2 and len(payload) == 1:
                kind, label = "activity", {0: "无活动目标", 1: "静止", 2: "活动"}.get(payload[0], "未知活动值")
            self.frames.appendleft(dict(at=block["at"], label=label, kind=kind,
                                         hex=packet.hex(" ").upper(), historical=block["historical"],
                                         offset_end=offset_end, epoch=self.epoch))

    def snapshot(self):
        now = time.monotonic()
        status_age = now - self.last_status_mono if self.last_status_mono is not None else None
        console_ok = self.connection == "connected" and status_age is not None and status_age < 10
        # Avoid advancing a board-relative age while its logs are unavailable.
        rx_age = None
        if console_ok and self.last_rx_ms is not None:
            rx_age = max(0, (self.uptime_ms - self.last_rx_ms) / 1000 + min(status_age, 3))
        return dict(started_at=self.started_at, elapsed_s=round(now - self.started_mono),
                    port=self.port, connection=self.connection, connection_note=self.connection_note,
                    console_ok=console_ok, console_age_s=round(status_age, 1) if status_age is not None else None,
                    status=self.status, new_bytes=self.new_bytes, valid_frames=self.valid_frames,
                    breaks=self.breaks, snapshot_count=self.snapshot_count, epoch=self.epoch,
                    presence=self.presence, presence_observed_at=self.presence_observed_at,
                    rx_age_s=round(rx_age, 1) if rx_age is not None else None,
                    frames=list(self.frames), logs=list(self.logs), samples=list(self.byte_samples))
