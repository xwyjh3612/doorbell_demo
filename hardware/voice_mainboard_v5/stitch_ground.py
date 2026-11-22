"""Run the established island-aware ground stitching on this V5 native board."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
source=(ROOT.parent/'voice_mainboard_v4/stitch_ground.py').read_text(encoding='utf8')
start=source.index('sys.argv=')
end=source.index('from shapely.geometry',start)
source=source[:start]+"from route_support import load\nr=load()\n"+source[end:]
source=source.replace('voice_mainboard_v4.kicad_pcb','voice_mainboard_v5.kicad_pcb')
exec(compile(source,str(Path(__file__).resolve()),'exec'),globals())
