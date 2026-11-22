"""Route the USB option before the enclosing modem D+ branch, then restore it."""
from pathlib import Path
import json,math
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
r,m=load();b=r.board;file=ROOT/'voice_mainboard_v5.kicad_pcb';held=[];report=[]
for t in list(b.GetTracks()):
    if t.GetNetname()=='M_USB_DP':held.append(t);b.Remove(t)
for net,eps in [('ESP_USB_DP20',[('R28','2'),('J22','2')]),('M_USB_DP',None)]:
    if eps is None:eps=[(f.GetReference(),pd.GetNumber()) for f in b.GetFootprints() for pd in f.Pads() if pd.GetNetname()==net]
    ends=[]
    for i,ep in enumerate(eps):
        name='USB_REWORK_'+net+'_'+str(i)
        try:
            if r.pad(*ep).GetAttribute()==p.PAD_ATTRIB_PTH:ends.append(ep)
            else:
                r.escapevia(name,ep,neck=.2)
                r.virtual[name].IsOnLayer=lambda li:li in [p.F_Cu,p.B_Cu]
                ends.append((name,0))
        except (RuntimeError,AssertionError) as e:
            ends.append(ep);print('USB escape failed',ep,str(e),flush=True)
    for a,z in zip(ends,ends[1:]):
        try:report.append({'net':net,'from':a,'to':z,'connected':True,**m.route(r,a,z,width=.2,step=.1,bounds=(.6,.6,99.4,74.4))})
        except RuntimeError as e:report.append({'net':net,'connected':False,'reason':str(e)})
        p.SaveBoard(str(file),b)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
for t in held:t.thisown=False
(ROOT/'exports/usb-option-rework.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
