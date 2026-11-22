"""Release foreign front-layer crossings under the relocated mux package.

The subsequent DRC connectivity report drives repair of these status nets.
No converter switching or RF track is changed.
"""
from pathlib import Path
import sys,json
import pcbnew as p
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import LineString,box
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
local=box(15.6,47.0,19.5,49.3);removed=[]
for t in list(b.GetTracks()):
    if isinstance(t,p.PCB_VIA) or t.GetLayer()!=p.F_Cu:continue
    if t.GetNetname()in ['GND','POWER_REG_5V','VIN_PROTECTED','UPS_BACKUP_5V','UPS_PG_OD','UPS_CTL_VCC','UPS_EXT_VALID']:continue
    sh=LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))])
    if sh.buffer(p.ToMM(t.GetWidth())/2).intersects(local):
        removed.append({'net':t.GetNetname(),'uuid':t.m_Uuid.AsString()});b.Remove(t)
p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'exports/released-mux-crossings.json').write_text(json.dumps(removed,indent=2)+'\n',encoding='utf8')
print('Released',len(removed),'foreign mux crossings')
