"""Open USB D- detours, ground RF/module pads, and turn the feedback resistor."""
from pathlib import Path
import json,math
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
r,m=load();b=r.board;file=ROOT/'voice_mainboard_v5.kicad_pcb';held=[];report=[]
for t in list(b.GetTracks()):
    if t.GetNetname() in ['ESP_USB_DM19','ESP_FB']:held.append(t);b.Remove(t)
fps={f.GetReference():f for f in b.GetFootprints()}
fps['R60'].SetOrientationDegrees(180)
data=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
for q in data['parts']:
    if q['ref']=='R60':q['angle']=180
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
p.SaveBoard(str(file),b)
refs={('R60','2'),('U1','36'),('U1','37'),('J11','2')}
for f in b.GetFootprints():
    for pd in f.Pads():
        if (f.GetReference(),pd.GetNumber()) not in refs:continue
        name='FINAL_GND_'+str(len(report));r.virtual[name]=pd
        try:
            r.escapevia(name+'_via',(name,0),neck=.2)
            report.append({'ref':f.GetReference(),'pin':pd.GetNumber(),'ground_escape':True})
        except (RuntimeError,AssertionError) as e:report.append({'ref':f.GetReference(),'pin':pd.GetNumber(),'ground_escape':False,'reason':str(e)})
        p.SaveBoard(str(file),b)
for net in ['ESP_FB','ESP_USB_DM19']:
    eps=[(f.GetReference(),pd.GetNumber()) for f in b.GetFootprints() for pd in f.Pads() if pd.GetNetname()==net]
    ends=[]
    for i,ep in enumerate(eps):
        if net=='ESP_FB':ends.append(ep);continue
        name='FINAL_DM_'+str(i)
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
        try:
            result=m.route(r,a,z,width=.2,step=.05 if net=='ESP_FB' else .1,bounds=(.6,.6,99.4,74.4))
            report.append({'net':net,'from':a,'to':z,'connected':True,**result})
        except RuntimeError as e:report.append({'net':net,'connected':False,'reason':str(e)})
        joined.append(z);ends.remove(z);p.SaveBoard(str(file),b)
# Restore the previously isolated modem bypass/test-point branch.
for ep in [('C12','1'),('U1','42')]:
    name='MODEM_FINISH_'+ep[0]
    try:
        r.escapevia(name,ep,neck=.3)
        r.virtual[name].IsOnLayer=lambda li:li in [p.F_Cu,p.B_Cu]
    except (RuntimeError,AssertionError):r.virtual[name]=r.pad(*ep)
try:
    report.append({'net':'MODEM_3V8','connected':True,**m.route(r,('MODEM_FINISH_C12',0),('MODEM_FINISH_U1',0),width=.4,step=.1,bounds=(55,5,76,24))})
except RuntimeError as e:report.append({'net':'MODEM_3V8','connected':False,'reason':str(e)})
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
for t in held:t.thisown=False
(ROOT/'exports/final-ground-rework.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
