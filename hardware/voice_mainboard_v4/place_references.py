"""Place readable reference silk against actual pad/graphic geometry.

Falls back to assembly-layer reference if no local silk space exists. Native
silkscreen DRC is run afterwards; no text violations are suppressed.
"""
from pathlib import Path
import sys,json,math
import pcbnew as p
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import Polygon,box,Point,LineString
from shapely.ops import unary_union
file=ROOT/'voice_mainboard_v4.kicad_pcb';b=p.LoadBoard(str(file))
def rect(bb):return box(*[p.ToMM(v)for v in [bb.GetLeft(),bb.GetTop(),bb.GetRight(),bb.GetBottom()]])
obstacles=[]
for fp in b.GetFootprints():
    fp.Reference().SetVisible(False)
    for pd in fp.Pads():
        q=pd.GetEffectivePolygon(p.F_Cu)
        for i in range(q.OutlineCount()):
            ring=q.COutline(i)
            pts=[(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]
            if len(pts)>2:obstacles.append(Polygon(pts).buffer(.2))
        if pd.GetDrillSize().x:obstacles.append(Point(p.ToMM(pd.GetPosition().x),p.ToMM(pd.GetPosition().y)).buffer(p.ToMM(pd.GetDrillSize().x)/2+.2))
    for item in fp.GraphicalItems():
        if item.GetLayer()==p.F_SilkS:obstacles.append(rect(item.GetBoundingBox()).buffer(.12))
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):obstacles.append(Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2+.12))
blocked=unary_union(obstacles);texts=[];report=[]
boardarea=box(.3,.3,99.7,74.7)
for fp in sorted(b.GetFootprints(),key=lambda f:(not f.GetReference().startswith(('U','J','SW')),f.GetReference())):
    name=fp.GetReference();text=fp.Reference();text.SetTextSize(p.VECTOR2I(p.FromMM(.8),p.FromMM(.8)))
    text.SetTextThickness(p.FromMM(.12));text.SetTextAngle(p.EDA_ANGLE(0,p.DEGREES_T));text.SetLayer(p.F_SilkS)
    center=(p.ToMM(fp.GetPosition().x),p.ToMM(fp.GetPosition().y));placed=False
    candidates=[(i*.4,j*.4)for i in range(-18,19)for j in range(-18,19)]
    for dx,dy in sorted(candidates,key=lambda pt:pt[0]**2+pt[1]**2):
        text.SetPosition(p.VECTOR2I(p.FromMM(center[0]+dx),p.FromMM(center[1]+dy)))
        shape=rect(text.GetBoundingBox()).buffer(.07)
        if not boardarea.contains(shape) or blocked.intersects(shape) or any(shape.intersects(t)for t in texts):continue
        text.SetVisible(True);texts.append(shape);placed=True;break
    if not placed:
        text.SetLayer(p.F_Fab);text.SetPosition(fp.GetPosition());text.SetVisible(True)
    report.append({'ref':name,'silkscreen':placed,'position_mm':[p.ToMM(text.GetPosition().x),p.ToMM(text.GetPosition().y)]})
p.SaveBoard(str(file),b)
(ROOT/'exports/reference-placement.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Reference silk placed:',sum(q['silkscreen']for q in report),'/',len(report))
