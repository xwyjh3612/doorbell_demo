"""Route outstanding non-supply gaps between explicitly escaped endpoints."""
from pathlib import Path
import json,math
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
r,m=load();b=r.board
d=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
objects={t.m_Uuid.AsString():t for t in b.GetTracks()};parents={}
for f in b.GetFootprints():
    for pad in f.Pads():objects[pad.m_Uuid.AsString()]=pad;parents[pad.m_Uuid.AsString()]=f.GetReference()
report=[]
for i,v in enumerate(d['unconnected_items']):
    it1,it2=v['items'];a,z=objects.get(it1['uuid']),objects.get(it2['uuid'])
    if a is None or z is None or a.GetNetname()!=z.GetNetname() or a.GetNetname() in ['GND','ESP_3V3']:continue
    net=a.GetNetname()
    choices=[]
    for obj in [a,z]:
        if isinstance(obj,(p.PAD,p.PCB_VIA)):choices.append([(p.ToMM(obj.GetPosition().x),p.ToMM(obj.GetPosition().y))])
        else:choices.append([(p.ToMM(pt.x),p.ToMM(pt.y)) for pt in [obj.GetStart(),obj.GetEnd()]])
    xy,zz=min(((x,y) for x in choices[0] for y in choices[1]),key=lambda q:math.dist(*q))
    ends=[]
    try:
        for j,(obj,point) in enumerate([(a,xy),(z,zz)]):
            key=f'VG_{i}_{j}'
            if isinstance(obj,p.PAD):ep=(parents[obj.m_Uuid.AsString()],obj.GetNumber())
            else:
                r.virtual[key]=r.Endpoint(net,point);ep=(key,0)
            layer=p.F_Cu if isinstance(obj,p.PAD) and obj.IsOnLayer(p.F_Cu) else p.B_Cu if isinstance(obj,p.PCB_VIA) else obj.GetLayer()
            if isinstance(obj,p.PCB_VIA):viaep=ep
            else:
                r.escapevia(key+'_via',ep,diameter=.6,drill=.3,neck=.2,layer=layer)
                viaep=(key+'_via',0)
            r.virtual[viaep[0]].IsOnLayer=lambda li:li in [p.F_Cu,p.B_Cu]
            ends.append(viaep)
        result=m.route(r,*ends,width=.2,step=.1,bounds=(.6,.6,99.4,74.4))
        report.append({'net':net,'connected':True,**result})
    except RuntimeError as e:
        report.append({'net':net,'connected':False,'reason':str(e)})
        print('Via gap remains',net,str(e),flush=True)
    p.SaveBoard(str(file),b)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
(ROOT/'exports/via-gap-connections.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Via gaps connected',sum(q['connected'] for q in report),'/',len(report))
