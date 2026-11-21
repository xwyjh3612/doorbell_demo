"""Observe an existing console log without opening or controlling serial."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]
STAMP = re.compile(r"\b[IWED] \((\d+)\) RADAR_GPIO5: (?:STATUS|HISTORY)\b")
CALL = re.compile(r"通话状态切换: (\w+) -> (\w+), reason=(\w+)")
AUDIO = re.compile(r"Send A:\d+ \[(\d+):(\d+)\] Recv A:\d+ \[(\d+):(\d+)\]")


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mark', choices=('external_unplugged', 'external_restored', 'measurement'))
    parser.add_argument('--note', default='', help='Local measurement notes; not firmware telemetry')
    parser.add_argument('--source', type=Path, help='Existing live console log; defaults to the radar collector')
    args = parser.parse_args()
    metadata = ROOT / 'build/power-test-service.json'
    if args.mark:
        meta = json.loads(metadata.read_text(encoding='utf-8-sig'))
        with (Path(meta['output']) / 'operator-marks.jsonl').open('a', encoding='utf-8') as output:
            output.write(json.dumps(dict(at=now(), action=args.mark, note=args.note), ensure_ascii=False)+'\n')
        print('Recorded manual test marker; external power is not measured automatically')
        return

    if args.source is None:
        radar_meta = json.loads((ROOT / 'build/radar-monitor-service.json').read_text(encoding='utf-8-sig'))
        source = Path(radar_meta['output']) / 'console.log'
    else:
        source = args.source.resolve(strict=True)
    output = ROOT / 'build' / ('power-test-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir()
    metadata.write_text(json.dumps(dict(output=str(output), source=str(source), started_at=now()), indent=2), encoding='utf-8')
    state = dict(started_at=now(), source=str(source), reset_observations=0,
                 console_gaps=0, firmware_uptime_ms=None, last_console_at=None,
                 call_state=None, audio_samples=0, electrical_measurements='not_measured',
                 result='awaiting_hardware_test')
    last_console_mono = None
    stale = False
    pending = ''

    def event(kind, **fields):
        with (output / 'events.jsonl').open('a', encoding='utf-8') as file:
            file.write(json.dumps(dict(at=now(), kind=kind, **fields), ensure_ascii=False)+'\n')

    print('Observing existing serial log: '+str(source), flush=True)
    print('Power-test records: '+str(output), flush=True)
    with source.open('r', encoding='utf-8', errors='replace') as console:
        console.seek(0, 2)  # Historical events are not part of this test.
        try:
            while True:
                chunk = console.read()
                pending += chunk
                while '\n' in pending:
                    line, pending = pending.split('\n', 1)
                    if line.strip():
                        state['last_console_at'] = now()
                        last_console_mono = time.monotonic()
                    stamp = STAMP.search(line)
                    if stamp:
                        uptime = int(stamp[1])
                        previous = state['firmware_uptime_ms']
                        if previous is not None and uptime + 1000 < previous:
                            state['reset_observations'] += 1
                            event('uptime_regression', previous_ms=previous, current_ms=uptime)
                        # Only use the sole radar task's clock; other tasks can interleave.
                        state['firmware_uptime_ms'] = uptime
                    call = CALL.search(line)
                    if call:
                        state['call_state'] = call[2]
                        event('call_state', previous=call[1], current=call[2], reason=call[3])
                    audio = AUDIO.search(line)
                    if audio:
                        state['audio_samples'] += 1
                        event('audio_statistics', sent_packets=int(audio[1]), sent_bytes=int(audio[2]),
                              received_packets=int(audio[3]), received_bytes=int(audio[4]))
                    if 'Brownout detector was triggered' in line:
                        event('brownout_reported')
                    elif 'Guru Meditation' in line or 'abort() was called' in line:
                        event('firmware_crash_reported')
                age = time.monotonic()-last_console_mono if last_console_mono is not None else None
                missing = age is not None and age > 10
                if missing and not stale:
                    state['console_gaps'] += 1
                    event('console_gap', note='May be power loss, cable loss or serial collector interruption')
                if stale and not missing:
                    event('console_resumed')
                stale = missing
                state['console_age_s'] = round(age, 1) if age is not None else None
                state['updated_at'] = now()
                temp = output / 'state.tmp'
                temp.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                temp.replace(output / 'state.json')
                time.sleep(1)
        except KeyboardInterrupt:
            print('Observation stopped', flush=True)


if __name__ == '__main__':
    main()
