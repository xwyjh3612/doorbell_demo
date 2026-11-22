"""Remove redundant stubs, reroute the remaining USB D+ net, join reset pads."""
from pathlib import Path
import json
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
r,m=load();b=r.board;held=[];report=[]
d=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
redundant={x['uuid'] for q in d['violations'] if q['type'] in ['via_dangling','track_dangling'] for x in q['items']}
for t in list(b.GetTracks()):
    if t.GetNetname()=='ESP_USB_DP20' or t.m_Uuid.AsString() in redundant:
        held.append(t);b.Remove(t)
p.SaveBoard(str(file),b)
for net,eps in [('ESP_USB_DP20',[('U7','14'),('R50','1'),('J22','2')])]:
    # Derive endpoints from the native pad contracts, rather than guessed GPIO pad numbers.
    eps=[(f.GetReference(),pd.GetNumber()) for f in b.GetFootprints() for pd in f.Pads() if pd.GetNetname()==net]
    eps.sort(key=lambda ep:(ep[0]!='U7',ep[0]))
    ends=[]
    for i,ep in enumerate(eps):
        name='FINAL_DP_'+str(i)
        if r.pad(*ep).GetAttribute()==p.PAD_ATTRIB_PTH:
            ends.append(ep);continue
        r.escapevia(name,ep,neck=.2)
        r.virtual[name].IsOnLayer=lambda layer:layer in [p.F_Cu,p.B_Cu]
        ends.append((name,0));p.SaveBoard(str(file),b)
    for a,z in zip(ends,ends[1:]):
        try:report.append({'net':net,'from':a,'to':z,'connected':True,**m.route(r,a,z,width=.2,step=.1,bounds=(.6,.6,99.4,74.4))})
        except RuntimeError as e:report.append({'net':net,'connected':False,'reason':str(e)})
        p.SaveBoard(str(file),b)
# Multiple pads with the same switch pin number still require physical copper.
pads=[pd for f in b.GetFootprints() if f.GetReference()=='SW2' for pd in f.Pads() if pd.GetNetname()=='ESP_EN']
for i,pd in enumerate(pads):r.virtual['RESET_'+str(i)]=pd
for i in range(1,len(pads)):
    try:report.append({'net':'ESP_EN','connected':True,**m.route(r,('RESET_0',0),('RESET_'+str(i),0),width=.2,step=.05,bounds=(16,35,29,43))})
    except RuntimeError as e:report.append({'net':'ESP_EN','connected':False,'reason':str(e)})
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
for t in held:t.thisown=False
(ROOT/'exports/final-signal-routes.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
