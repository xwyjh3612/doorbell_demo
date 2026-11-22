"""Route wide ESP supply backbone and checked smaller peripheral branches."""
from pathlib import Path
import json, math
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
r,m=load();b=r.board;report=[];ends={}
def join(a,z,width,neck=.3,diameter=.6,drill=.3):
    try:
        for ep in [a,z]:
            if ep in ends:continue
            pd=r.pad(*ep)
            if pd.GetAttribute()==p.PAD_ATTRIB_PTH:ends[ep]=ep;continue
            name='ESP_SUP_'+str(len(ends))
            r.escapevia(name,ep,diameter=diameter,drill=drill,neck=neck)
            r.virtual[name].IsOnLayer=lambda li:li in [p.F_Cu,p.B_Cu]
            ends[ep]=(name,0)
        result=m.route(r,ends[a],ends[z],width=width,step=.1,bounds=(.6,.6,99.4,74.4))
        report.append({'from':a,'to':z,'width_mm':width,'connected':True,**result})
    except RuntimeError as e:
        report.append({'from':a,'to':z,'width_mm':width,'connected':False,'reason':str(e)})
        print('Supply remaining',a,z,str(e),flush=True)
    p.SaveBoard(str(file),b)
# Main ESP32 load gets a deliberately wider route.  Local bypass stays short.
for a,z,w in [(('L4','2'),('C60','1'),.7),(('C60','1'),('U7','2'),.7)]:join(a,z,w,neck=.4,diameter=.8,drill=.4)
eps=[(f.GetReference(),pd.GetNumber()) for f in b.GetFootprints() for pd in f.Pads() if pd.GetNetname()=='ESP_3V3']
joined=[('L4','2'),('C60','1'),('U7','2')]
remaining=[ep for ep in eps if ep not in joined]
while remaining:
    a,z=min(((a,z) for a in joined for z in remaining),key=lambda pair:math.dist(r.pos(r.pad(*pair[0])),r.pos(r.pad(*pair[1]))))
    # Feed-forward resistor and small logic IC pads use short 0.2mm necks.
    join(a,z,.35,neck=.2)
    joined.append(z);remaining.remove(z)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
(ROOT/'exports/esp-supply-routes.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('ESP supply routes',sum(q['connected'] for q in report),'/',len(report))
