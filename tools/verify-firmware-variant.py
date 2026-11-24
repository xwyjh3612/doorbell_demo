"""Verify optional radar source inclusion and actual linked symbols."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--variant', choices=('voice', 'voice-radar', 'voice-radar60', 'mainboard-v6', 'mainboard-v6-radar60'), required=True)
args = parser.parse_args()
build = args.root / 'build'
enabled = args.variant in ('voice-radar', 'voice-radar60', 'mainboard-v6-radar60')
power_enabled = args.variant.startswith('mainboard-v6')
config = (build / 'config/sdkconfig.h').read_text(encoding='utf-8')
assert ('#define CONFIG_VOICE_RADAR_ENABLE 1' in config) == enabled, 'Wrong build configuration'
assert ('#define CONFIG_VOICE_RADAR_R60 1' in config) == (args.variant in ('voice-radar60', 'mainboard-v6-radar60')), 'Wrong model'
assert ('#define CONFIG_VOICE_POWER_MONITOR_ENABLE 1' in config) == power_enabled
commands = json.loads((build / 'compile_commands.json').read_text(encoding='utf-8'))
compiled = any(Path(cmd['file']).name == 'radar_presence.c' for cmd in commands)
assert compiled == enabled, 'Radar compilation inclusion does not match variant'
assert any(Path(cmd['file']).name == 'radar_telemetry.cpp' for cmd in commands) == enabled
assert any(Path(cmd['file']).name == 'power_monitor.cpp' for cmd in commands) == power_enabled
nm = shutil.which('xtensa-esp32s3-elf-nm')
if not nm:
    raise SystemExit('ESP-IDF nm tool not found; activate the ESP-IDF environment')
symbols = subprocess.check_output([nm, '--defined-only', str(build / 'doorbell_demo.elf')], text=True)
for name in ('radar_presence_start', 'radar_presence_register_console', 'radar_reader', 'radar_telemetry_start'):
    linked = any(line.split()[-1] == name for line in symbols.splitlines() if line.split())
    assert linked == enabled, f'Unexpected radar symbol inclusion: {name}'
for name in ('power_monitor_start', 'power_monitor_register_console'):
    assert any(line.split()[-1] == name for line in symbols.splitlines() if line.split()) == power_enabled, name
print(f'{args.variant}: config, compilation and linked radar/power symbols verified')
