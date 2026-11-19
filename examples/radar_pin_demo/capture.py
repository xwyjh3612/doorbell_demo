"""Read the native USB console; does not send commands to the radar module."""
import argparse
from pathlib import Path
import sys
import time
import serial
from serial.tools import list_ports

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", required=True, help="ESP32 native USB COM port, not CH343")
parser.add_argument("--seconds", type=float, default=40)
parser.add_argument("--rx", type=int, choices=(5, 43, 44), default=44)
parser.add_argument("--radar-baud", type=int, default=115200,
                    choices=(9600, 19200, 38400, 57600, 115200, 256000))
parser.add_argument("--output", type=Path)
args = parser.parse_args()
if args.seconds <= 0:
    parser.error("--seconds must be positive")
device = next((p for p in list_ports.comports()
               if p.device.casefold() == args.port.casefold()), None)
if device is None:
    parser.error(f"{args.port} is not connected")
if (device.vid, device.pid) != (0x303A, 0x1001):
    parser.error("Use the ESP32 native USB Serial/JTAG port (303A:1001), "
                 "not the CH343/UART connector; no commands were sent")
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
    # anything. A native USB port alone does not identify the running firmware.
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
            if b"RADAR_PIN: STATUS rx=" in probe or b"RADAR_PIN: READY console=native-USB" in probe:
                break
            if len(probe) > 8192:
                del probe[:-4096]
    else:
        raise SystemExit("New radar_pin_demo was not identified within 8s; "
                         "no commands were sent. Check firmware and USB port.")
    # USB Serial/JTAG does not reset the board here. Space the CLI commands
    # to let its command queue process the pin/baud changes before clearing.
    pending = [f"radar rx {args.rx}", f"radar baud {args.radar_baud}",
               "radar raw on", "radar clear", "radar status"]
    send_at = time.monotonic() + 0.5
    end = send_at + 0.3 * len(pending) + args.seconds
    while time.monotonic() < end:
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
