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
    ('incoming', 'ring.aac', (800, 1000), ((0, .35), (.5, .85), (2, 2.35), (2.5, 2.85))),
    ('outgoing', 'outgoing.aac', (450,), ((0, 1),)),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    args = parser.parse_args()
    if not args.ffmpeg:
        parser.error('Install FFmpeg or specify --ffmpeg PATH')
    preview = ROOT / 'build/call-tones'
    preview.mkdir(parents=True, exist_ok=True)
    records = []
    for name, filename, frequencies, pulses in TONES:
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
        print(f'{name}: {target.name}; preview: {wav}')
    (ROOT / 'main/call-tones.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
