"""Close real native-reported non-ground gaps using two-layer searches."""
from pathlib import Path
import json,math
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
r,m=load()
b=r.board
d=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
objects={t.m_Uuid.AsString():t for t in b.GetTracks()}
parents={}
for fp in b.GetFootprints():
    for pad in fp.Pads():
        objects[pad.m_Uuid.AsString()]=pad
        parents[pad.m_Uuid.AsString()]=fp.GetReference()


def setup(obj,it,other,key):
    if isinstance(obj,p.PAD):
        return parents[obj.m_Uuid.AsString()],obj.GetNumber()
    xy=it['pos']
    if isinstance(obj,p.PCB_VIA):
        xy={'x':p.ToMM(obj.GetPosition().x),'y':p.ToMM(obj.GetPosition().y)}
    else:
        candidates=[(p.ToMM(v.x),p.ToMM(v.y)) for v in [obj.GetStart(),obj.GetEnd()]]
        target=(other['pos']['x'],other['pos']['y'])
        x,y=min(candidates,key=lambda z:math.dist(z,target))
        xy={'x':x,'y':y}
    ep=r.Endpoint(obj.GetNetname(),(xy['x'],xy['y']))
    ep.IsOnLayer=(lambda layer:layer in [p.F_Cu,p.B_Cu]) if isinstance(obj,p.PCB_VIA) else (lambda layer,used=obj.GetLayer():layer==used)
    r.virtual[key]=ep
    return key,0


report=[]
for i,v in enumerate(d['unconnected_items']):
    it1,it2=v['items']
    a,z=objects.get(it1['uuid']),objects.get(it2['uuid'])
    if a is None or z is None or a.GetNetname()!=z.GetNetname() or a.GetNetname() in ['GND','ESP_3V3']:continue
    src,goal=setup(a,it1,it2,'GA'+str(i)),setup(z,it2,it1,'GZ'+str(i))
    x1,y1=r.pos(r.pad(*src));x2,y2=r.pos(r.pad(*goal))
    bounds=(max(.6,min(x1,x2)-6),max(.6,min(y1,y2)-6),min(99.4,max(x1,x2)+6),min(74.4,max(y1,y2)+6))
    try:
        result=m.route(r,src,goal,width=.2,step=.05,bounds=bounds)
        report.append({'net':a.GetNetname(),'connected':True,**result})
    except RuntimeError as e:
        report.append({'net':a.GetNetname(),'connected':False,'reason':str(e)})
        print('Gap remains',a.GetNetname(),str(e),flush=True)
    p.SaveBoard(str(file),b)
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(file),b)
(ROOT/'exports/gap-connections.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Connected native signal gaps',sum(q['connected'] for q in report),'/',len(report))
