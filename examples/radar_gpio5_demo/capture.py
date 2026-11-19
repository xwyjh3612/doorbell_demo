"""Read the GPIO5 radar demo's CH343 console; no commands are sent to the radar."""
import argparse
from pathlib import Path
import sys
import time
import serial
from serial.tools import list_ports

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", required=True, help="CH343 UART console COM port")
parser.add_argument("--seconds", type=float, default=40)
parser.add_argument("--rx", type=int, choices=(5, 6, 8), default=5)
parser.add_argument("--radar-baud", type=int, default=115200,
                    choices=(9600, 19200, 38400, 57600, 115200, 256000))
parser.add_argument("--output", type=Path)
parser.add_argument("--passive", action="store_true",
                    help="Read logs without configuring or clearing; --history optionally queries saved data")
parser.add_argument("--history", action="store_true",
                    help="Read saved RX bytes at start/end without clearing or changing configuration")
args = parser.parse_args()
if args.seconds <= 0:
    parser.error("--seconds must be positive")
if args.history and not args.passive:
    parser.error("Use --history with --passive to preserve received data")
device = next((p for p in list_ports.comports()
               if p.device.casefold() == args.port.casefold()), None)
if device is None:
    parser.error(f"{args.port} is not connected")
if (device.vid, device.pid) != (0x1A86, 0x55D3):
    parser.error("Use the board's CH343 UART console port (1A86:55D3); "
                 "no commands were sent")
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)

port = serial.Serial()
port.port = args.port
port.baudrate = 115200
port.timeout = 0.1
port.dtr = False
port.rts = False
log = args.output.open("wb") if args.output else None
try:
    port.open()
    # Verify the installed app by reading its recurring status before sending
    # anything. The CH343 port alone does not identify the running firmware.
    probe = bytearray()
    identify_until = time.monotonic() + 8
    while time.monotonic() < identify_until:
        data = port.read(port.in_waiting or 1)
        if data:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            if log:
                log.write(data)
            probe.extend(data)
            if b"RADAR_GPIO5: STATUS rx=" in probe or b"RADAR_GPIO5: READY console=UART0" in probe:
                break
            if len(probe) > 8192:
                del probe[:-4096]
    else:
        raise SystemExit("New radar_gpio5_demo was not identified within 8s; "
                         "no commands were sent. Check firmware and USB port.")
    # DTR/RTS remain deasserted. Space the CLI commands
    # to let its command queue process the pin/baud changes before clearing.
    pending = [] if args.passive else [f"radar rx {args.rx}", f"radar baud {args.radar_baud}",
                                      "radar raw on", "radar clear", "radar status"]
    send_at = time.monotonic() + 0.5
    end = send_at + 0.3 * len(pending) + args.seconds
    history_end_sent = False
    if args.history:
        port.write(b"radar history\r\n")
    while time.monotonic() < end:
        if args.history and not history_end_sent and time.monotonic() >= end - 2:
            port.write(b"radar history\r\n")
            history_end_sent = True
        if pending and time.monotonic() >= send_at:
            port.write((pending.pop(0) + "\r\n").encode("ascii"))
            send_at = time.monotonic() + 0.3
        data = port.read(port.in_waiting or 1)
        if data:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            if log:
                log.write(data)
finally:
    port.close()
    if log:
        log.close()
