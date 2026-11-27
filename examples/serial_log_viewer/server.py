"""Local TTL log viewer. Follow the existing collector without claiming its port."""
import argparse
from collections import deque
from datetime import datetime, timedelta, timezone
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
TEST_TIMEZONE = timezone(timedelta(hours=8))
EXCLUDED_CLASSIFICATIONS = {"test-supervisor-interruption", "test-server-interruption",
                           "test-firmware-transition", "test-user-power-interruption"}


def test_time(value):
    """UART timestamps have no offset; runners write UTC with a trailing Z."""
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=TEST_TIMEZONE)
        return stamp
    except ValueError:
        return None


class CallHistory:
    """Read-only summaries of existing batch files, without touching test control."""

    def __init__(self, root=ROOT):
        self.build = (Path(root) / "build").resolve()
        self.lock = threading.RLock()
        self.cache = {}

    def read_json(self, path):
        # State writers overwrite in place. Keep the last complete snapshot
        # during a partial write; never hold the file open between requests.
        path = Path(path).resolve()
        if not path.is_relative_to(self.build):
            return {}
        try:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            cached = self.cache.get(path)
            if cached and cached[0] == signature:
                return cached[1]
            if stat.st_size > 32 * 1024 * 1024:
                return {}
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                return {}
            self.cache[path] = (signature, data)
            return data
        except (OSError, ValueError):
            return self.cache.get(path, (None, {}))[1]

    def batches(self):
        found = []
        for path in self.build.glob("*/state.json"):
            state = self.read_json(path)
            if isinstance(state.get("attempts"), list) and state.get("targetSecondsPerRound"):
                annotations = self.read_json(path.parent / "operator-annotations.json").get("attempts", [])
                state = dict(state)
                state["attempts"] = [self.annotated_attempt(attempt, annotations) for attempt in state["attempts"]]
                found.append((path.parent.name, state))
        found.sort(key=lambda item: item[1].get("updatedAt") or item[1].get("startedAt") or "", reverse=True)
        return found

    @staticmethod
    def annotated_attempt(attempt, annotations):
        if not isinstance(attempt, dict) or not isinstance(annotations, list):
            return attempt
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            evidence = annotation.get("classificationEvidence")
            if (isinstance(annotation.get("attempt"), int) and annotation["attempt"] == attempt.get("attempt")
                    and annotation.get("connectedAt") == attempt.get("connectedAt")
                    and annotation.get("failureClassification") == "test-user-power-interruption"
                    and isinstance(evidence, dict) and evidence.get("source") == "user-report"):
                return {**attempt, "failureClassification": annotation["failureClassification"],
                        "classificationEvidence": evidence}
        return attempt

    def attempt_result(self, batch, attempt):
        number = attempt.get("attempt")
        if not isinstance(number, int) or number < 1:
            return {}
        directory = self.build / batch / f"attempt-{number}"
        result = self.read_json(directory / "results.json") or self.read_json(directory / "progress.json")
        # Some old batches copy records from a different cohort. Never attach
        # another call's metadata just because its attempt number matches.
        if attempt.get("connectedAt") and result.get("connectedAt") != attempt["connectedAt"]:
            return {}
        return result

    @staticmethod
    def reason(attempt, result, status):
        classification = attempt.get("failureClassification")
        error = attempt.get("error") or result.get("error") or ""
        evidence = attempt.get("failureEvent") or result.get("failureEvent") or ""
        afe = attempt.get("firstAfeAlert") or result.get("firstAfeAlert")
        if classification == "test-server-interruption":
            return "测试服务器中断，已排除正式轮数"
        if classification == "test-supervisor-interruption":
            return "电脑／测试程序中断，已排除正式轮数"
        if classification == "test-user-power-interruption":
            return "用户报告拔掉UPS供电，已按用户要求排除正式轮数；原始错误与日志保留"
        if status in {"calling", "connected"}:
            if status == "connected" and result.get("afeAlerts") and result.get("afePolicy") == "observe":
                return "已记录AFE验收异常，继续观察音频是否恢复"
            return "正在等待接通" if status == "calling" else "正在观察双向音频"
        if status == "stale":
            return "测试状态超过45秒未更新，当前是否仍通话待确认"
        if status == "passed":
            return "完成目标时长，测试判定通过"
        if "Interrupt wdt timeout" in error + evidence:
            return "ESP32中断看门狗超时，CPU长时间未正常处理中断；具体阻塞位置需解码调用栈"
        if "Guru Meditation" in error + evidence:
            return "ESP32发生程序崩溃；具体原因需使用同版固件解码调用栈"
        if afe or "AFE" in error or "AFE: Ringbuffer" in evidence:
            if result.get("afePolicy") == "observe" and result.get("audioObservationCompleted"):
                return "出现过AFE告警，音频观察已完成目标时长；按验收规则判失败"
            return "已观察到AFE音频缓冲溢出；底层原因尚未确认"
        if re.search(r"MATREADY|modem.*boot|modem.*restart", error + evidence, re.I):
            return "已观察到4G模组重新启动；重启原因尚未确认"
        if "Bidirectional audio stopped" in error:
            return "双向音频数据连续超过12秒未更新"
        if "No bidirectional audio" in error:
            return "接通后20秒内未观察到双向音频"
        if "设备来电" in error:
            return "App未出现设备来电状态，呼叫未接通"
        if "Offer cached" in error:
            return "设备未出现待接听事件，呼叫未接通"
        if "Peer failed" in error or "webrtc_disconnected" in evidence:
            return "通话连接断开；具体原因需结合关键日志判断"
        if "deadline" in error or "timeout" in error.lower():
            return "呼叫／观察超时"
        return "测试未通过，查看原始错误与关键日志" if error else "记录未给出明确失败原因"

    def record(self, batch, attempt, state, now, active=False):
        result = self.attempt_result(batch, attempt)
        started = result.get("callStartedAt")
        hangup_requested = result.get("hangupRequestedAt")
        start_kind = "发起呼叫" if started else "测试启动（含初始化）"
        commands = self.build / batch / f"attempt-{attempt.get('attempt')}" / "operator-commands.jsonl"
        # Existing device-originated calls already have exact command times.
        if result and commands.resolve().is_relative_to(self.build):
            try:
                if commands.stat().st_size < 1024 * 1024:
                    for line in commands.read_text(encoding="utf-8").splitlines():
                        try:
                            command = json.loads(line)
                            if not started and command.get("command") == "cmd ring":
                                started, start_kind = command.get("at"), "设备发起呼叫"
                            elif command.get("command") == "cmd close":
                                hangup_requested = command.get("at")
                        except (ValueError, AttributeError):
                            continue
            except OSError:
                pass
        started = started or attempt.get("startedAt") or result.get("startedAt")
        connected = attempt.get("connectedAt") or result.get("connectedAt")
        completed = attempt.get("completedAt") or result.get("completedAt")
        samples = result.get("audioSamples") or []
        last_audio = next((sample.get("at") for sample in reversed(samples)
                           if isinstance(sample, dict) and sample.get("sentBytes", 0) > 0 and sample.get("receivedBytes", 0) > 0),
                          attempt.get("lastAudioAt")) if isinstance(samples, list) else attempt.get("lastAudioAt")
        classification = attempt.get("failureClassification")
        excluded = classification in EXCLUDED_CLASSIFICATIONS
        updated = test_time(state.get("updatedAt"))
        fresh = bool(updated and (now - updated).total_seconds() < 45)
        if active:
            status = ("connected" if connected else "calling") if fresh else "stale"
        elif excluded:
            status = "excluded"
        else:
            status = "passed" if attempt.get("passed") is True else ("failed" if connected else "setup-failed")
        # completedAt is runner cleanup completion, not proof of exact hangup.
        ended = result.get("disconnectedAt") or result.get("endedAt")
        end_kind = "挂断记录" if ended else None
        if not ended and not active and completed:
            ended, end_kind = completed, "测试结束（含收尾）"
        start_stamp = test_time(connected)
        end_stamp = now if active and fresh else test_time(ended or last_audio)
        duration = max(0, (end_stamp - start_stamp).total_seconds()) if start_stamp and end_stamp else None
        evidence = list(dict.fromkeys(str(line).strip() for line in [
            attempt.get("firstAfeAlert"), attempt.get("failureEvent"),
            result.get("firstAfeAlert"), result.get("failureEvent"),
        ] if line))
        power = attempt.get("powerCondition")
        if power == "Phone charger -> UPS board without battery -> device; no battery backup; voltage not independently measured":
            power = "手机充电器 → UPS板（未装电池）→ 设备；无电池保底，电压未独立测量"
        reason = self.reason(attempt, result, status)
        if classification == "test-firmware-transition":
            reason = "为刷入AFE修复固件主动结束；未完成30分钟，保留记录且不计正式轮次"
        afe_line = attempt.get("firstAfeAlert") or result.get("firstAfeAlert") or ""
        afe_match = LOG_TIMESTAMP.match(afe_line)
        afe_at = test_time(afe_match.group()) if afe_match else None
        after_afe = [sample for sample in samples if isinstance(sample, dict)
                     and sample.get("sentBytes", 0) > 0 and sample.get("receivedBytes", 0) > 0
                     and test_time(sample.get("at")) and afe_at and test_time(sample["at"]) > afe_at] if isinstance(samples, list) else []
        continuation = (test_time(after_afe[-1]["at"]) - afe_at).total_seconds() if after_afe else None
        stopped_for_afe = bool(status == "failed" and "AFE feed buffer overflow" in (attempt.get("error") or result.get("error") or "")
                               and result.get("afePolicy") != "observe" and hangup_requested and after_afe)
        if stopped_for_afe:
            reason = "AFE告警触发验收失败；告警后仍有双向音频，随后测试程序主动挂断"
        return {"attempt": attempt.get("attempt"), "round": attempt.get("round") if active else attempt.get("countedRound"),
                "direction": attempt.get("direction") or result.get("direction"), "status": status,
                "started_at": started, "start_kind": start_kind, "connected_at": connected, "ended_at": ended, "end_kind": end_kind,
                "completed_at": completed, "observation_ended_at": result.get("observationEndedAt"),
                "failure_detected_at": result.get("failureDetectedAt") or result.get("afeFailureDetectedAt"), "last_audio_at": last_audio,
                "duration_seconds": duration, "observed_seconds": attempt.get("observedSeconds") or result.get("observedSeconds"),
                "active": active, "fresh": fresh, "excluded": excluded,
                "reason": reason, "hangup_requested_at": hangup_requested,
                "audio_continued_after_afe_seconds": continuation, "test_stopped_on_afe": stopped_for_afe,
                "afe_policy": result.get("afePolicy"), "audio_observation_completed": result.get("audioObservationCompleted", False),
                "error": attempt.get("error") or result.get("error"), "evidence": evidence,
                "power_condition": power,
                "audio_samples": attempt.get("audioSamples") if isinstance(attempt.get("audioSamples"), int) else len(samples),
                "bidirectional_samples": attempt.get("bidirectionalSamples"),
                "afe_alerts": attempt.get("afeAlerts", result.get("afeAlerts", 0)),
                "ttl_counts": attempt.get("observedTtlCounts"),
                "classification_evidence": attempt.get("classificationEvidence")}

    def snapshot(self, batch=None):
        with self.lock:
            batches = self.batches()
            choices = [{"id": name, "started_at": state.get("startedAt"),
                        "target_rounds": state.get("requestedConnectedRounds"), "finished": state.get("finished", False)}
                       for name, state in batches]
            now = datetime.now(timezone.utc)
            if not batches:
                return {"batches": [], "records": [], "active": None, "server_time": now.isoformat()}
            batch = batch or batches[0][0]
            state = next((state for name, state in batches if name == batch), None)
            if state is None:
                raise ValueError("未找到该测试批次")
            records, completed, passed, excluded, setup_failed = [], 0, 0, 0, 0
            for original in state["attempts"]:
                if not isinstance(original, dict):
                    continue
                attempt = dict(original)
                is_excluded = attempt.get("failureClassification") in EXCLUDED_CLASSIFICATIONS
                if attempt.get("connectedAt") and not is_excluded:
                    completed += 1
                    passed += attempt.get("passed") is True
                    attempt["countedRound"] = completed
                else:
                    attempt["countedRound"] = None
                excluded += is_excluded and bool(attempt.get("connectedAt"))
                setup_failed += not attempt.get("connectedAt")
                records.append(self.record(batch, attempt, state, now))
            active = self.record(batch, state["active"], state, now, True) if isinstance(state.get("active"), dict) else None
            if active:
                active["round"] = completed + 1
                records.append(active)
            return {"batches": choices, "batch": batch, "server_time": now.isoformat(), "updated_at": state.get("updatedAt"),
                    "phase": state.get("phase"), "batch_error": state.get("error"), "active": active,
                    "target_rounds": state.get("requestedConnectedRounds"), "target_seconds": state.get("targetSecondsPerRound"),
                    "summary": {"completed": completed, "passed": passed, "failed": completed - passed,
                                "excluded": excluded, "setup_failed": setup_failed}, "records": records[::-1]}


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
        # Call testing writes this collector directly. A stale radar service
        # file must not pin "live" to an old panic log after the collector changes.
        candidates = []
        call_log = self.build / "esp32-real-call-live.log"
        if call_log.exists():
            candidates.append(call_log)
        metadata = self.build / "radar-monitor-service.json"
        try:
            output = Path(json.loads(metadata.read_text(encoding="utf-8-sig"))["output"])
            path = (output / "console.log").resolve()
            if path.is_relative_to(self.build.resolve()) and path.exists():
                candidates.append(path)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None

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
    calls = CallHistory()
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
            elif parsed.path == "/api/calls":
                try:
                    self.respond(calls.snapshot(query.get("batch", [None])[0]))
                except ValueError:
                    self.send_error(400)
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
