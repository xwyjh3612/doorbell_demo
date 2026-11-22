"""Use the existing obstacle-aware silk placement on the actual V5 board."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
source=(ROOT.parent/'voice_mainboard_v4/place_references.py').read_text(encoding='utf8')
source=source.replace('voice_mainboard_v4.kicad_pcb','voice_mainboard_v5.kicad_pcb')
exec(compile(source,str(Path(__file__).resolve()),'exec'),globals())
