"""Check both copper faces for PTH collisions and shorten local decoupling."""
from pathlib import Path
import json,math,sys
import pcbnew as p
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO/'build/cad-tools/route-python'))
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import polygonize,unary_union
FILE=ROOT/'voice_mainboard_v8_a18.kicad_pcb';b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()}
def xy(q):return p.ToMM(q.x),p.ToMM(q.y)
def court(f):
    lines=[];others=[]
    for g in f.GraphicalItems():
        if g.GetLayer()not in [p.F_CrtYd,p.B_CrtYd]:continue
        if g.GetShape()==p.S_SEGMENT:lines.append(LineString([xy(g.GetStart()),xy(g.GetEnd())]))
        elif g.GetShape()==p.S_CIRCLE:others.append(Point(xy(g.GetStart())).buffer(math.dist(xy(g.GetStart()),xy(g.GetEnd()))+.03))
    return unary_union([*polygonize(lines),*others])
def padsh(d,layer):
    q=d.GetEffectivePolygon(layer);out=[]
    for i in range(q.OutlineCount()):
        ch=q.COutline(i);pts=[xy(ch.CPoint(j))for j in range(ch.PointCount())]
        if len(pts)>2:out.append(Polygon(pts))
    return out
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'));boardpoly=Polygon(data['mechanical']['outline_mm']).buffer(-.6,join_style=2)
def legal(f):
    layer=f.GetLayer();sh=court(f)
    if not boardpoly.covers(sh):return False
    if layer==p.F_Cu and f.GetReference()!='SW1' and sh.intersects(box(30,30,43,43)):return False
    for other in fps.values():
        if other is f:continue
        if other.GetLayer()==layer:
            if sh.intersects(court(other).buffer(.08,join_style=2)):return False
            continue
        for d in f.Pads():
            for o in other.Pads():
                if o.GetAttribute()!=p.PAD_ATTRIB_PTH and d.GetAttribute()!=p.PAD_ATTRIB_PTH:continue
                # Opposite-face surface mount parts are allowed to overlap,
                # while every PTH annulus crosses both copper faces.
                for face in [p.F_Cu,p.B_Cu]:
                    if not d.IsOnLayer(face)or not o.IsOnLayer(face):continue
                    if d.GetNetname()==o.GetNetname()and d.GetNetname():continue
                    if any(a.distance(z)<.205 for a in padsh(d,face)for z in padsh(o,face)):return False
    return True
changes=[]
# Native DRC identified these backside/PTH collisions. Keep every original
# footprint and net, and move the affected small part, never the PTH signal.
for r in ['U19','R69','C72','R71','TP12']:
    f=fps[r];old=xy(f.GetPosition());angle=f.GetOrientationDegrees();found=False
    choices=sorted(((old[0]+dx*.25,old[1]+dy*.25)for dx in range(-32,33)for dy in range(-32,33)),key=lambda z:math.dist(old,z))
    for x,y in choices:
        f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
        if legal(f):found=True;break
    if not found:raise RuntimeError('Unresolved PTH conflict '+r)
    changes.append({'ref':r,'from':old,'to':[x,y],'reason':'both-face pad clearance'})

for r,target in [('C4',('U2','4')),('C59',('U13','4')),('C68',('U16','5'))]:
    f=fps[r];old=xy(f.GetPosition());oldangle=f.GetOrientationDegrees()
    targetpad=next(d for d in fps[target[0]].Pads()if d.GetNumber()==target[1]);goal=xy(targetpad.GetPosition())
    best=None
    for angle in [0,90,180,270]:
        f.SetOrientationDegrees(angle)
        choices=sorted(((goal[0]+dx*.25,goal[1]+dy*.25)for dx in range(-24,25)for dy in range(-24,25)),key=lambda z:math.dist(goal,z))
        for x,y in choices:
            f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
            if not legal(f):continue
            pd=next(d for d in f.Pads()if d.GetNumber()=='1');distance=math.dist(xy(pd.GetPosition()),goal)
            if best is None or distance<best[0]:best=(distance,x,y,angle)
            break
    if best is None:raise RuntimeError('No decoupling placement '+r)
    distance,x,y,angle=best;f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));f.SetOrientationDegrees(angle)
    changes.append({'ref':r,'from':old,'to':[x,y],'reason':'local supply decoupling','pad_center_distance_mm':distance})
for q in data['parts']:
    f=fps[q['ref']];q.update(x=xy(f.GetPosition())[0],y=xy(f.GetPosition())[1],angle=f.GetOrientationDegrees())
p.SaveBoard(str(FILE),b);(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'exports/power-placement-refinement.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(changes,ensure_ascii=False,indent=2))
