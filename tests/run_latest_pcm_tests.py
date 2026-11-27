"""Compile the actual source adapter with real host threads and platform stubs."""
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[1]
out = root / 'build/host-tests/test_latest_pcm_audio_src.exe'
out.parent.mkdir(exist_ok=True, parents=True)
subprocess.run([
    str(root / 'build/host-tools/ziglang/zig.exe'), 'c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
    '-I', str(root / 'tests/host/pcm'), '-I', str(root / 'main'),
    '-I', str(root / 'managed_components/espressif__esp_capture/interface'),
    '-I', str(root / 'managed_components/espressif__esp_capture/include'),
    str(root / 'main/latest_pcm_audio_src.cpp'), str(root / 'tests/host/test_latest_pcm_audio_src.cpp'),
    '-o', str(out)
], check=True, cwd=root)
subprocess.run([str(out)], check=True, cwd=root, timeout=30)
