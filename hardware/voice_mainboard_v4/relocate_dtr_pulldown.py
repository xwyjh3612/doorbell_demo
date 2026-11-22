"""Place the static DTR pulldown on connected ground and reconnect its input."""
from pathlib import Path
import json,math,pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
scope={'__file__':str(ROOT/'join_ground_components.py')}
exec(compile((ROOT/'join_ground_components.py').read_text(encoding='utf8').split('for iteration in range')[0],'ground_graph','exec'),scope)
r=scope['r'];m=scope['m'];b=r.board;graph=scope['graph'];held=[]
from shapely.geometry import Point,LineString,box
from shapely.ops import unary_union
fp=next(f for f in b.GetFootprints()if f.GetReference()=='R5')
for t in list(b.GetTracks()):
    if t.GetNetname()=='ESP_DTR4':b.Remove(t);held.append(t)
nodes,groups=graph();main=unary_union([nodes[i][1]for i in groups[0]if nodes[i][0]==p.F_Cu])
obstacles=[]
for f in b.GetFootprints():
    if f.GetReference()=='R5':continue
    # Keep manufacturing courtyards apart, including bodies with small pads.
    bbox=f.GetBoundingBox(False,False)
    obstacles.append(box(p.ToMM(bbox.GetLeft()),p.ToMM(bbox.GetTop()),p.ToMM(bbox.GetRight()),p.ToMM(bbox.GetBottom())).buffer(.1))
blocked=unary_union(obstacles)
choices=sorted([(x*.25,y*.25)for x in range(160,211)for y in range(124,164)],key=lambda xy:math.dist(xy,(46,35)))
selected=None
for x,y in choices:
    body=box(x-1.4,y-.75,x+1.4,y+.75)
    if blocked.intersects(body)or not main.buffer(-.15).contains(Point(x+.825,y)):continue
    fp.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
    # Ensure both pads clear existing other-net copper, not just bodies.
    ok=True
    for pd in fp.Pads():
        shape=unary_union(r.polygons(pd,p.F_Cu)).buffer(.205)
        for t in b.GetTracks():
            if t.GetNetname()==pd.GetNetname():continue
            if isinstance(t,p.PCB_VIA):sh=Point(r.pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2)
            elif t.GetLayer()==p.F_Cu:
                a,z=t.GetStart(),t.GetEnd();sh=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]).buffer(p.ToMM(t.GetWidth())/2)
            else:continue
            if shape.intersects(sh):ok=False;break
        if not ok:break
    if ok:selected=(x,y);break
if selected is None:raise RuntimeError('No checked DTR resistor placement')
endpoints=[(f.GetReference(),pd.GetNumber())for f in b.GetFootprints()for pd in f.Pads()if pd.GetNetname()=='ESP_DTR4']
report=[]
for endpoint in endpoints:
    if endpoint==('R5','1'):continue
    try:report.append({'to':endpoint,'connected':True,**m.route(r,('R5',1),endpoint,width=.2,step=.05,bounds=(28,12,60,45))})
    except RuntimeError as e:report.append({'to':endpoint,'connected':False,'reason':str(e)})
drc=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
tails={i['uuid']for v in drc['violations']if v['type']=='via_dangling'for i in v['items']}
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString()in tails:b.Remove(t);held.append(t)
p.SaveBoard(str(file),b)
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
for q in d['parts']:
    if q['ref']=='R5':q.update(x=selected[0],y=selected[1],angle=fp.GetOrientationDegrees())
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'exports/dtr-pulldown-placement.json').write_text(json.dumps({'position_mm':selected,'connections':report},indent=2)+'\n',encoding='utf8')
print('DTR resistor:',selected,report)
