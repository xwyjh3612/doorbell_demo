"""Generate original intercom call tones and encode ADTS AAC with FFmpeg."""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
RATE = 16000
DURATION = 4
TONES = (
    ('incoming', 'ring.aac', (440, 480), ((0, 2),)),
    ('outgoing', 'outgoing.aac', (450,), ((0, 1),)),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--only', choices=('incoming', 'outgoing'))
    args = parser.parse_args()
    if not args.ffmpeg:
        parser.error('Install FFmpeg or specify --ffmpeg PATH')
    preview = ROOT / 'build/call-tones'
    preview.mkdir(parents=True, exist_ok=True)
    records = []
    for name, filename, frequencies, pulses in TONES:
        if args.only and args.only != name:
            continue
        samples = array('h')
        for index in range(RATE * DURATION):
            t, value = index / RATE, 0.0
            for start, end in pulses:
                if start <= t < end:
                    # Ten millisecond fades prevent sharp clicks at each edge.
                    fade = min(1.0, (t - start) / .01, (end - t) / .01)
                    envelope = .5 - .5 * math.cos(math.pi * fade)
                    value = .45 * envelope * sum(math.sin(2 * math.pi * f * (t - start))
                                                for f in frequencies) / len(frequencies)
                    if name == 'incoming':
                        # Familiar electronic desk-phone trill; less piercing
                        # than the earlier 800/1000 Hz notification-like beeps.
                        value *= .75 + .25 * math.cos(2 * math.pi * 20 * (t - start))
                    break
            samples.append(round(value * 32767))
        if sys.byteorder != 'little':
            samples.byteswap()
        wav = preview / (name + '.wav')
        with wave.open(str(wav), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(samples.tobytes())
        target = ROOT / 'main' / filename
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(wav),
                        '-map_metadata', '-1', '-c:a', 'aac', '-profile:a', 'aac_low',
                        '-ar', str(RATE), '-ac', '1', '-b:a', '32k', '-f', 'adts', str(target)], check=True)
        records.append(dict(name=name, file=filename, sample_rate=RATE, channels=1,
                            duration_seconds=DURATION, frequencies_hz=frequencies,
                            pulses_seconds=pulses, size=target.stat().st_size,
                            sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        if name == 'incoming':
            records[-1]['tremolo_hz'] = 20
        print(f'{name}: {target.name}; preview: {wav}')
    manifest = ROOT / 'main/call-tones.json'
    if args.only and manifest.exists():
        records += [r for r in json.loads(manifest.read_text(encoding='utf-8')) if r['name'] != args.only]
    manifest.write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
