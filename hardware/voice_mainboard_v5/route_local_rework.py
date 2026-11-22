"""Connect relocated low-current pins; leave ESP supply to be routed last."""
from pathlib import Path
import json,math
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
r,m=load();b=r.board;report=[]
for net in ['M_SIM_CLK','M_SIM_RESET','SIM_CLK','SIM_RESET','SIM_VCC','ESP_EN']:
    endpoints=[(f.GetReference(),pad.GetNumber()) for f in b.GetFootprints() for pad in f.Pads() if pad.GetNetname()==net]
    endpoints.sort(key=lambda e:(e[0] not in ['U1','U7'],e[0],e[1]))
    joined=[endpoints.pop(0)]
    while endpoints:
        a,z=min(((a,z) for a in joined for z in endpoints),key=lambda az:math.dist(r.pos(r.pad(*az[0])),r.pos(r.pad(*az[1]))))
        xy,zz=r.pos(r.pad(*a)),r.pos(r.pad(*z))
        bounds=(max(.6,min(xy[0],zz[0])-6),max(.6,min(xy[1],zz[1])-6),min(99.4,max(xy[0],zz[0])+6),min(74.4,max(xy[1],zz[1])+6))
        try:
            result=m.route(r,a,z,width=.2,step=.05,bounds=bounds)
            report.append({'net':net,'from':a,'to':z,'connected':True,**result})
        except RuntimeError as e:report.append({'net':net,'from':a,'to':z,'connected':False,'reason':str(e)})
        joined.append(z);endpoints.remove(z);p.SaveBoard(str(file),b)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
(ROOT/'exports/local-pin-rework.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Local rework connected',sum(q['connected'] for q in report),'/',len(report))
