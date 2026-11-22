"""Free the boost feedback resistor's ground pad from a closed routing pocket."""
from pathlib import Path
import sys,json
import pcbnew as p
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
from route_multilayer import route
b=r.board;d=json.loads((root/'design.json').read_text(encoding='utf8'));held=list(b.GetTracks())
for t in held:
    if t.GetNetname()=='UPS_BOOST_FB':b.Remove(t)
f=next(f for f in b.GetFootprints()if f.GetReference()=='R41')
f.SetPosition(p.VECTOR2I(p.FromMM(21.25),p.FromMM(64.75)))
next(v for v in d['parts']if v['ref']=='R41').update(x=21.25,y=64.75,side='B',angle=f.GetOrientationDegrees())
try:
    r.escapevia('r41_ground',('R41',2),neck=.2)
    r.escapevia('r41_fb',('R41',1),neck=.2)
    # Narrow RNS lead exits are routed on the surface before the rear resistor.
    r.route(('U9',3),('R40',2),width=.2,step=.025,bounds=(14,56,23,64))
    route(r,('R40',2),('r41_fb',0),width=.2,step=.05,bounds=(14,56,25,68))
finally:
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    (root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
