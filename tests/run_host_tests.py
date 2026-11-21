"""Run the production call controller against deterministic host framework stubs.

Usage: python tests/run_host_tests.py --compiler path/to/zig.exe
Also accepts clang or gcc. Zig can be installed locally with:
python -m pip install --target build/host-tools ziglang
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--compiler")
parser.add_argument("--idf", help="ESP-IDF directory containing the Mbed TLS sources")
args = parser.parse_args()
compiler = args.compiler or shutil.which("clang") or shutil.which("gcc")
local_zig = root / "build/host-tools/ziglang/zig.exe"
if not compiler and local_zig.exists():
    compiler = str(local_zig)
if not compiler:
    sys.exit("Set --compiler to a host C compiler or install ziglang into build/host-tools.")

output = root / "build/host-tests"
output.mkdir(parents=True, exist_ok=True)
source = (root / "main/webrtc_mqtt.c").read_text(encoding="utf-8")
# Only platform includes are replaced; every production function is compiled unchanged.
source = re.sub(r"^\s*#include[^\n]*", "", source, flags=re.MULTILINE)
(output / "firmware_under_test.inc").write_text(source, encoding="utf-8")
binary = output / ("test_call_control.exe" if sys.platform == "win32" else "test_call_control")
command = [compiler]
if Path(compiler).stem == "zig":
    command.append("cc")
command += ["-std=gnu11", "-g", "-I", str(root / "tests/host"),
            "-I", str(root / "main"), "-I", str(output),
            str(root / "tests/host/test_call_control.c"), "-o", str(binary)]
subprocess.run(command, check=True, cwd=root)
subprocess.run([str(binary)], check=True, cwd=root)

idf = args.idf or os.environ.get("IDF_PATH")
description = root / "build/project_description.json"
if not idf and description.exists():
    idf = json.loads(description.read_text(encoding="utf-8"))["idf_path"]
if not idf:
    sys.exit("Set --idf or IDF_PATH to run the OTA tests with the real Mbed TLS implementation.")
mbedtls = Path(idf) / "components/mbedtls/mbedtls"
md5_object = output / "md5.o"
md5_command = [compiler] + (["cc"] if Path(compiler).stem == "zig" else [])
md5_command += ["-DMBEDTLS_CONFIG_FILE=\"host_mbedtls_config.h\"",
                "-I", str(root / "tests/host"), "-I", str(mbedtls / "include"),
                "-c", str(mbedtls / "library/md5.c"), "-o", str(md5_object)]
subprocess.run(md5_command, check=True, cwd=root)
ota_source = (root / "main/otaupgrade.cpp").read_text(encoding="utf-8")
ota_source = re.sub(r"^\s*#include[^\n]*", "", ota_source, flags=re.MULTILINE)
(output / "ota_under_test.inc").write_text(ota_source, encoding="utf-8")
ota_binary = output / ("test_ota.exe" if sys.platform == "win32" else "test_ota")
if Path(compiler).stem == "zig":
    ota_command = [compiler, "c++"]
else:
    cpp_name = "g++" if Path(compiler).stem == "gcc" else "clang++"
    ota_command = [str(Path(compiler).with_name(cpp_name + Path(compiler).suffix))]
ota_command += ["-std=c++17", "-DMBEDTLS_CONFIG_FILE=\"host_mbedtls_config.h\"",
                "-I", str(root / "tests/host"), "-I", str(root / "main"),
                "-I", str(output), "-I", str(mbedtls / "include"),
                str(root / "tests/host/test_ota.cpp"), str(md5_object), "-o", str(ota_binary)]
subprocess.run(ota_command, check=True, cwd=root)
subprocess.run([str(ota_binary)], check=True, cwd=root)

# Run the same mailbox implementation used by ML307 against real host threads.
udp_binary = output / ("test_latest_udp_packet.exe" if sys.platform == "win32" else "test_latest_udp_packet")
udp_command = ota_command[:2] if Path(compiler).stem == "zig" else ota_command[:1]
udp_command += ["-std=c++17", "-g", "-I", str(root / "main"),
                str(root / "tests/host/test_latest_udp_packet.cpp"), "-o", str(udp_binary)]
if sys.platform != "win32":
    udp_command.append("-pthread")
subprocess.run(udp_command, check=True, cwd=root)
subprocess.run([str(udp_binary)], check=True, cwd=root, timeout=60)

radar_binary = output / ("test_radar_frame_parser.exe" if sys.platform == "win32" else "test_radar_frame_parser")
radar_command = [compiler] + (["cc"] if Path(compiler).stem == "zig" else [])
radar_command += ["-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(root / "main"),
                  str(root / "tests/host/test_radar_frame_parser.c"), "-o", str(radar_binary)]
subprocess.run(radar_command, check=True, cwd=root)
subprocess.run([str(radar_binary)], check=True, cwd=root, timeout=30)

readings_binary = output / ("test_radar_readings.exe" if sys.platform == "win32" else "test_radar_readings")
readings_command = [compiler] + (["cc"] if Path(compiler).stem == "zig" else [])
readings_command += ["-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(root / "main"),
                     str(root / "tests/host/test_radar_readings.c"), "-o", str(readings_binary)]
subprocess.run(readings_command, check=True, cwd=root)
subprocess.run([str(readings_binary)], check=True, cwd=root, timeout=30)

telemetry_source = (root / "main/radar_telemetry.cpp").read_text(encoding="utf-8")
guard = re.search(r"static bool radar_telemetry_allowed\(void\)\n\{.*?\n\}", telemetry_source, re.S)
assert guard, "Production radar upload guard missing"
(output / "radar_telemetry_guard_under_test.inc").write_text(guard[0], encoding="utf-8")
guard_binary = output / ("test_radar_telemetry.exe" if sys.platform == "win32" else "test_radar_telemetry")
guard_command = ota_command[:2] if Path(compiler).stem == "zig" else ota_command[:1]
guard_command += ["-std=c++17", "-I", str(root / "main"), "-I", str(output),
                  str(root / "tests/host/test_radar_telemetry.cpp"), "-o", str(guard_binary)]
subprocess.run(guard_command, check=True, cwd=root)
subprocess.run([str(guard_binary)], check=True, cwd=root, timeout=30)

# Run the actual outgoing signaling function against a framework role stub.
# This catches the answered-call -> hangup -> originate regression.
signaling_source = (root / "main/mqtt_signaling.cpp").read_text(encoding="utf-8")
ring_start = signaling_source.index("void mqtt_sig_send_ring(const char *target)\n{")
ring_end = signaling_source.index("void mqtt_sig_trigger_offer(void)", ring_start)
(output / "outgoing_ring_under_test.inc").write_text(signaling_source[ring_start:ring_end], encoding="utf-8")
role_binary = output / ("test_outgoing_ice_role.exe" if sys.platform == "win32" else "test_outgoing_ice_role")
role_command = ota_command[:2] if Path(compiler).stem == "zig" else ota_command[:1]
role_command += ["-std=c++20", "-I", str(output), str(root / "tests/host/test_outgoing_ice_role.cpp"), "-o", str(role_binary)]
subprocess.run(role_command, check=True, cwd=root)
subprocess.run([str(role_binary)], check=True, cwd=root, timeout=30)

# The actual ICE delivery function must not reset an established peer on MQTT
# recovery, or free the configuration strings retained by that peer.
ice_start = signaling_source.index("static void mqtt_sig_apply_ice(")
ice_end = signaling_source.index("\nvoid mqtt_sig_set_device_id", ice_start)
(output / "connected_ice_refresh_under_test.inc").write_text(signaling_source[ice_start:ice_end], encoding="utf-8")
ice_binary = output / ("test_connected_ice_refresh.exe" if sys.platform == "win32" else "test_connected_ice_refresh")
ice_command = ota_command[:2] if Path(compiler).stem == "zig" else ota_command[:1]
ice_command += ["-std=c++20", "-I", str(root / "main"), "-I", str(output),
                str(root / "tests/host/test_connected_ice_refresh.cpp"), "-o", str(ice_binary)]
subprocess.run(ice_command, check=True, cwd=root)
subprocess.run([str(ice_binary)], check=True, cwd=root, timeout=30)

# Compile the production UDP URC handler and Disconnect together. The stub
# rejects AT commands from inside the locked receive callback, reproducing the
# FIFO-overrun deadlock without hanging the test process.
modem_udp_source = (root / "components/esp-ml307/src/ml307/ml307_udp.cc").read_text(encoding="utf-8")
handler_start = modem_udp_source.index("void Ml307Udp::handleUrc(")
handler_end = modem_udp_source.index("\nMl307Udp::~Ml307Udp()", handler_start)
close_start = modem_udp_source.index("void Ml307Udp::Disconnect()")
close_end = modem_udp_source.index("\nint Ml307Udp::Send(", close_start)
(output / "udp_fifo_under_test.inc").write_text(
    modem_udp_source[handler_start:handler_end] + modem_udp_source[close_start:close_end], encoding="utf-8")
fifo_binary = output / ("test_udp_fifo_overflow.exe" if sys.platform == "win32" else "test_udp_fifo_overflow")
fifo_command = ota_command[:2] if Path(compiler).stem == "zig" else ota_command[:1]
fifo_command += ["-std=c++20", "-I", str(output), str(root / "tests/host/test_udp_fifo_overflow.cpp"), "-o", str(fifo_binary)]
subprocess.run(fifo_command, check=True, cwd=root)
subprocess.run([str(fifo_binary)], check=True, cwd=root, timeout=10)

# Run actual MQTT client and recovery code. The UART stub rejects recursive AT
# sends on the receive callback; concurrent readers keep the original client
# while two recovery callers run 200 reconnects.
def without_includes(text):
    return re.sub(r"^\s*#include[^\n]*", "", text, flags=re.MULTILINE)

mqtt_dir = root / "components/esp-ml307"
for name, source_path in (
    ("mqtt_interface_under_test.inc", mqtt_dir / "include/mqtt.h"),
    ("mqtt_client_header_under_test.inc", mqtt_dir / "src/ml307/ml307_mqtt.h"),
    ("mqtt_client_under_test.inc", mqtt_dir / "src/ml307/ml307_mqtt.cc"),
):
    (output / name).write_text(without_includes(source_path.read_text(encoding="utf-8")), encoding="utf-8")

def production_function(text, signature):
    start = text.index(signature)
    begin = text.index("{", start)
    depth = 1
    end = begin + 1
    while depth:
        if text[end] == "{": depth += 1
        elif text[end] == "}": depth -= 1
        end += 1
    return text[start:end]

network_source = (root / "main/network_4g.cpp").read_text(encoding="utf-8")
for name, text, signature in (
    ("mqtt_network_init_under_test.inc", network_source, "void initMqtt(){"),
    ("mqtt_network_get_under_test.inc", network_source, "Mqtt* GetMqttInstance() {"),
    ("mqtt_connection_dispatch_under_test.inc", signaling_source, "static void dispatch_mqtt_connection(bool connected)\n{"),
    ("mqtt_connection_handler_under_test.inc", signaling_source, "static void mqtt_connection_handler(bool connected)\n{"),
    ("mqtt_setup_callbacks_under_test.inc", signaling_source, "static void setup_mqtt_callbacks(void)\n{"),
):
    (output / name).write_text(production_function(text, signature), encoding="utf-8")
mqtt_binary = output / ("test_mqtt_recovery.exe" if sys.platform == "win32" else "test_mqtt_recovery")
mqtt_command = ota_command[:2] if Path(compiler).stem == "zig" else ota_command[:1]
mqtt_command += ["-std=c++20", "-I", str(output), str(root / "tests/host/test_mqtt_recovery.cpp"), "-o", str(mqtt_binary)]
if sys.platform != "win32": mqtt_command.append("-pthread")
subprocess.run(mqtt_command, check=True, cwd=root)
subprocess.run([str(mqtt_binary)], check=True, cwd=root, timeout=30)

main_source = (root / "main/main.cpp").read_text(encoding="utf-8")
(output / "modem_restart_under_test.inc").write_text(
    production_function(main_source, "static int modem_cli(int argc, char **argv) {"), encoding="utf-8")
restart_binary = output / ("test_modem_restart.exe" if sys.platform == "win32" else "test_modem_restart")
restart_command = ota_command[:2] if Path(compiler).stem == "zig" else ota_command[:1]
restart_command += ["-std=c++20", "-I", str(root / "main"), "-I", str(output),
                    str(root / "tests/host/test_modem_restart.cpp"), "-o", str(restart_binary)]
subprocess.run(restart_command, check=True, cwd=root)
subprocess.run([str(restart_binary)], check=True, cwd=root, timeout=10)
