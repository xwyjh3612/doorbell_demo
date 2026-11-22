"""Orient the USB option resistor for west modem/east host and free RF ground."""
from pathlib import Path
import json,math
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
r,m=load();b=r.board;file=ROOT/'voice_mainboard_v5.kicad_pcb';held=[];report=[]
for t in list(b.GetTracks()):
    if t.GetNetname() in ['ESP_USB_DP20','M_USB_DP']:held.append(t);b.Remove(t)
fps={f.GetReference():f for f in b.GetFootprints()};fps['R28'].SetOrientationDegrees(0)
fps['R28'].SetPosition(p.VECTOR2I(p.FromMM(81.1),p.FromMM(33.5)))
data=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
for q in data['parts']:
    if q['ref']=='R28':q.update(x=81.1,y=33.5,angle=0)
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for n in ['36','37']:
    name='RF_GROUND_'+n
    try:
        r.escapevia(name,('U1',n),neck=.2)
        report.append({'ground_pin':n,'escaped':True})
    except (RuntimeError,AssertionError) as e:report.append({'ground_pin':n,'escaped':False,'reason':str(e)})
p.SaveBoard(str(file),b)
for net in ['M_USB_DP','ESP_USB_DP20']:
    eps=[(f.GetReference(),pd.GetNumber()) for f in b.GetFootprints() for pd in f.Pads() if pd.GetNetname()==net]
    eps.sort(key=lambda e:(e[0]!='U1' if net!='ESP_USB_DP20' else e[0]!='U7',e[0]))
    ends=[]
    for i,ep in enumerate(eps):
        name='OPT_'+net+'_'+str(i)
        try:
            if r.pad(*ep).GetAttribute()==p.PAD_ATTRIB_PTH:ends.append(ep)
            else:
                r.escapevia(name,ep,neck=.2)
                r.virtual[name].IsOnLayer=lambda li:li in [p.F_Cu,p.B_Cu]
                ends.append((name,0))
        except (RuntimeError,AssertionError):ends.append(ep)
    joined=[ends.pop(0)]
    while ends:
        a,z=min(((a,z) for a in joined for z in ends),key=lambda pair:math.dist(r.pos(r.pad(*pair[0])),r.pos(r.pad(*pair[1]))))
        try:report.append({'net':net,'from':a,'to':z,'connected':True,**m.route(r,a,z,width=.2,step=.1,bounds=(.6,.6,99.4,74.4))})
        except RuntimeError as e:report.append({'net':net,'connected':False,'reason':str(e)})
        joined.append(z);ends.remove(z);p.SaveBoard(str(file),b)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
for t in held:t.thisown=False
(ROOT/'exports/option-layout-final.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
