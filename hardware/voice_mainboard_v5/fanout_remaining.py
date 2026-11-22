"""Release enclosing failed nets, add fine-pitch fanouts, then route between vias."""
from pathlib import Path
import json,math
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
r,m=load();b=r.board
nets=['M_RX_1V8','M_TX_1V8','M_SIM_RESET','MODEM_1V8','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19','I2S_MIC_BCLK14']
held=[]
for t in list(b.GetTracks()):
    if t.GetNetname() in nets:held.append(t);b.Remove(t)
report=[]
for net in nets:
    endpoints=[(f.GetReference(),pad.GetNumber()) for f in b.GetFootprints() for pad in f.Pads() if pad.GetNetname()==net]
    endpoints.sort(key=lambda e:(0 if e[0] in ['U1','U7'] else 1,e[0],e[1]))
    fanouts=[]
    for i,ep in enumerate(endpoints):
        name='FO_'+net+'_'+str(i)
        try:
            r.escapevia(name,ep,diameter=.6,drill=.3,neck=.2)
            r.virtual[name].IsOnLayer=lambda layer:layer in [p.F_Cu,p.B_Cu]
            fanouts.append((name,0))
            report.append({'net':net,'pad':ep,'fanout':True})
        except RuntimeError as e:
            report.append({'net':net,'pad':ep,'fanout':False,'reason':str(e)})
            fanouts.append(ep)
        p.SaveBoard(str(file),b)
    if not fanouts:continue
    joined=[fanouts.pop(0)]
    while fanouts:
        src,goal=min(((a,z) for a in joined for z in fanouts),key=lambda az:math.dist(r.pos(r.pad(*az[0])),r.pos(r.pad(*az[1]))))
        x1,y1=r.pos(r.pad(*src));x2,y2=r.pos(r.pad(*goal))
        bounds=(max(.6,min(x1,x2)-8),max(.6,min(y1,y2)-8),min(99.4,max(x1,x2)+8),min(74.4,max(y1,y2)+8))
        try:
            result=m.route(r,src,goal,width=.2,step=.1,bounds=bounds)
            report.append({'net':net,'connected':True,**result})
        except RuntimeError as e:
            report.append({'net':net,'connected':False,'reason':str(e)})
        joined.append(goal);fanouts.remove(goal)
        p.SaveBoard(str(file),b)
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(file),b)
for t in held:t.thisown=False
(ROOT/'exports/fine-pitch-fanouts.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Fine-pitch fanouts:',sum(q.get('fanout') is True for q in report),'connections:',sum(q.get('connected') is True for q in report),'failed:',sum(q.get('connected') is False or q.get('fanout') is False for q in report))
