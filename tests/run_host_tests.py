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
