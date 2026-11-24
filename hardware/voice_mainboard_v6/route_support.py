"""Load the existing obstacle-aware router, including both antenna keepouts."""
from pathlib import Path
import sys, types
ROOT=Path(__file__).resolve().parent


def load():
    wrapper=(ROOT.parent/'voice_mainboard_v4/connect_ground_lobes.py').read_text(encoding='utf8').split('pairs =')[0]
    wrapper=wrapper.replace("file = ROOT / 'voice_mainboard_v4.kicad_pcb'", "file = ROOT / 'voice_mainboard_v6.kicad_pcb'")
    scope={'__file__':str(ROOT/'route_support.py')}
    exec(compile(wrapper,'v5_router_loader','exec'),scope)
    return scope['r']
