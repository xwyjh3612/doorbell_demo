"""Capture the demo console. Requires pyserial (included in ESP-IDF Python)."""
import argparse
from pathlib import Path
import sys
import time

import serial

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", required=True)
parser.add_argument("--seconds", type=float, default=30, help="Capture duration; with --scan, seconds per baud")
baud_options = parser.add_mutually_exclusive_group()
baud_options.add_argument("--radar-baud", type=int, choices=(9600, 19200, 38400, 57600, 115200, 256000))
baud_options.add_argument("--scan", action="store_true", help="Try six common baud rates; does not configure the radar")
parser.add_argument("--reset", action="store_true", help="Reset ESP32 using the USB serial RTS line")
parser.add_argument("--output", type=Path)
args = parser.parse_args()
if args.seconds <= 0:
    parser.error("--seconds must be positive")
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)

console = serial.Serial()
console.port = args.port
console.baudrate = 115200
console.timeout = 0.1
console.dtr = False
console.rts = False
output = args.output.open("wb") if args.output else None
try:
    console.open()
    if args.reset:
        console.rts = True
        time.sleep(0.1)
        console.rts = False
    # Allow boot and console initialization without discarding startup output.
    rates = [9600, 115200, 256000, 57600, 38400, 19200] if args.scan else [args.radar_baud]
    command_at = time.monotonic() + 2
    deadline = command_at + args.seconds * len(rates)
    rate_index = 0
    while time.monotonic() < deadline:
        if rate_index < len(rates) and time.monotonic() >= command_at:
            rate = rates[rate_index]
            command = f"radar baud {rate}" if rate else "radar status"
            console.write((command + "\r\n").encode("ascii"))
            rate_index += 1
            command_at += args.seconds
        data = console.read(console.in_waiting or 1)
        if data:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            if output:
                output.write(data)
finally:
    console.close()
    if output:
        output.close()
