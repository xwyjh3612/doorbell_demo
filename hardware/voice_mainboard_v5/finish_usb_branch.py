"""Join the USB host option branch with a finer local two-layer search."""
from pathlib import Path
import json
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
r,m=load();b=r.board
file=ROOT/'voice_mainboard_v5.kicad_pcb'
d=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
held=[]
redundant={it['uuid'] for q in d['violations'] if q['type'] in ['via_dangling','track_dangling'] for it in q['items']}
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString() in redundant:held.append(t);b.Remove(t)
objects={t.m_Uuid.AsString():t for t in b.GetTracks()}
targets=[]
for q in d['unconnected_items']:
    if all('[ESP_USB_DP20]' in it['description'] for it in q['items']):
        for it in q['items']:
            t=objects.get(it['uuid'])
            if t is not None and t.GetLayer()==p.B_Cu:
                targets.extend([(p.ToMM(pt.x),p.ToMM(pt.y)) for pt in [t.GetStart(),t.GetEnd()]])
report=[]
for i,xy in enumerate(targets):
    name='USB_FINISH_'+str(i)
    r.virtual[name]=r.Endpoint('ESP_USB_DP20',xy)
    r.virtual[name].IsOnLayer=lambda layer:layer==p.B_Cu
    try:
        result=m.route(r,('R28','2'),(name,0),width=.2,step=.05,bounds=(72,23,96,40))
        report.append({'connected':True,'target_mm':xy,**result});break
    except RuntimeError as e:
        report.append({'connected':False,'target_mm':xy,'reason':str(e)})
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
for t in held:t.thisown=False
(ROOT/'exports/usb-branch-route.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
