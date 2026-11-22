"""Join actual copper islands; native zone-origin gaps are not real coordinates."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
source=(ROOT.parent/'voice_mainboard_v4/join_ground_components.py').read_text(encoding='utf8')
start=source.index("scope={'__file__'")
end=source.index('from shapely.geometry',start)
source=source[:start]+"from two_layer_support import load\nr,m=load()\nb=r.board\n"+source[end:]
source=source.replace('voice_mainboard_v4.kicad_pcb','voice_mainboard_v5.kicad_pcb')
exec(compile(source,str(Path(__file__).resolve()),'exec'),globals())
