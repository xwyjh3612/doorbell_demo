"""Probe a reverse-side input bypass close to the actual boost VIN pad.

Writes a separate candidate. Adopt only after DRC and netlist parity.
"""
from pathlib import Path
import sys,math,json
import pcbnew as p
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
b=r.board;f=next(x for x in b.GetFootprints() if x.GetReference()=='C40')
old=[r.pos(pd) for pd in f.Pads()];held=[]
for t in list(b.GetTracks()):
    if isinstance(t,p.PCB_VIA):continue
    if any(math.dist(z,(p.ToMM(pt.x),p.ToMM(pt.y)))<.05 for z in old for pt in [t.GetStart(),t.GetEnd()]):
        held.append(t);b.Remove(t)
f.Flip(f.GetPosition(),False)
def court(fp):
    fp.BuildCourtyardCaches();q=fp.GetCourtyard(p.B_CrtYd);sh=[]
    for n in range(q.OutlineCount()):
        ch=q.COutline(n);pts=[(p.ToMM(ch.CPoint(k).x),p.ToMM(ch.CPoint(k).y))for k in range(ch.PointCount())]
        if len(pts)>=3:sh.append(Polygon(pts))
    return unary_union(sh)
courts=unary_union([court(x)for x in b.GetFootprints()if x!=f and x.IsFlipped()])
obs={net:[]for net in ['BAT_SENSE_IN','GND']}
for fp in b.GetFootprints():
    if fp==f:continue
    for pd in fp.Pads():
        if not pd.IsOnLayer(p.B_Cu):continue
        for net in obs:
            if pd.GetNetname()!=net:obs[net].extend(sh.buffer(.205) for sh in r.polygons(pd,p.B_Cu))
for t in b.GetTracks():
    if not isinstance(t,p.PCB_VIA)and t.GetLayer()!=p.B_Cu:continue
    shape=Point(r.pos(t))if isinstance(t,p.PCB_VIA)else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))])
    radius=p.ToMM(t.GetWidth(p.B_Cu)if isinstance(t,p.PCB_VIA)else t.GetWidth())/2
    for net in obs:
        if t.GetNetname()!=net:obs[net].append(shape.buffer(radius+.205))
obs={net:unary_union(sh)for net,sh in obs.items()}
source=r.pos(r.pad('U9',4));found=[]
for angle in [0,90,180,270]:
    f.SetOrientationDegrees(angle)
    for ix in range(55,90):
        for iy in range(215,249):
            xy=(ix*.25,iy*.25);f.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
            if courts.intersects(court(f)):continue
            if any(obs[pd.GetNetname()].intersects(sh)for pd in f.Pads()for sh in r.polygons(pd,p.B_Cu)):continue
            distance=math.dist(source,r.pos(r.pad('C40',1)))
            if distance<3:found.append((distance,xy,angle))
assert found,'No reverse-side location within 3mm VIN'
distance,xy,angle=min(found)
f.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])));f.SetOrientationDegrees(angle)
r.escapevia('C40_BAT',('C40',1),diameter=.6,drill=.3,neck=.5)
r.route(('C40_BAT',0),('U9',4),width=.25,step=.025,bounds=(12,52,24,64))
r.escapevia('C40_GND',('C40',2),diameter=.6,drill=.3,neck=.5)
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(root/'exports/boost-bypass-candidate.kicad_pcb'),b)
(root/'exports/boost-bypass-candidate.json').write_text(json.dumps({'x':xy[0],'y':xy[1],'angle':angle,'side':'B','vin_pad_distance_mm':distance},indent=2)+'\n',encoding='utf8')
print('Candidate saved',xy,angle,distance,flush=True)
