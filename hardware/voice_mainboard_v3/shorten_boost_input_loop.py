"""Move the boost input bypass beside VIN, preserving the inductor/SW loop.

The former C40 location was 7mm from VIN. Only copper ending at its old pads
is removed; independent DRC must follow the new short connection and ground.
"""
from pathlib import Path
import sys,json,math
import pcbnew as p
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
b=r.board;fp=next(f for f in b.GetFootprints()if f.GetReference()=='C40')
old=[r.pos(pd)for pd in fp.Pads()];held=[]
for t in list(b.GetTracks()):
    if isinstance(t,p.PCB_VIA):continue
    if t.GetNetname()not in ['BAT_SENSE_IN','GND']:continue
    pts=[(p.ToMM(pt.x),p.ToMM(pt.y))for pt in [t.GetStart(),t.GetEnd()]]
    if any(math.dist(a,z)<.05 for a in pts for z in old):held.append(t);b.Remove(t)
from shapely.geometry import Point,LineString,box,Polygon
from shapely.ops import unary_union
obs={net:[]for net in ['BAT_SENSE_IN','GND']};courts=[]
def court(f):
    f.BuildCourtyardCaches();q=f.GetCourtyard(p.F_CrtYd);sh=[]
    for n in range(q.OutlineCount()):
        ch=q.COutline(n)
        pts=[(p.ToMM(ch.CPoint(k).x),p.ToMM(ch.CPoint(k).y))for k in range(ch.PointCount())]
        if len(pts)>=3:sh.append(Polygon(pts))
    return unary_union(sh)
for other in b.GetFootprints():
    if other.GetReference()=='C40':continue
    if not other.IsFlipped():
        courts.append(court(other))
    for pd in other.Pads():
        if not pd.IsOnLayer(p.F_Cu):continue
        for net in obs:
            if pd.GetNetname()!=net:obs[net].extend(sh.buffer(.205)for sh in r.polygons(pd,p.F_Cu))
for t in b.GetTracks():
    if not isinstance(t,p.PCB_VIA)and t.GetLayer()!=p.F_Cu:continue
    sh=Point(r.pos(t))if isinstance(t,p.PCB_VIA)else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))])
    radius=p.ToMM(t.GetWidth(p.F_Cu)if isinstance(t,p.PCB_VIA)else t.GetWidth())/2
    for net in obs:
        if t.GetNetname()!=net:obs[net].append(sh.buffer(radius+.205))
obs={net:unary_union(sh)for net,sh in obs.items()};courts=unary_union(courts)
source=r.pos(r.pad('U9',4));candidates=[]
for angle in [0,90,180,270]:
    fp.SetOrientationDegrees(angle)
    for ix in range(50,90):
        for iy in range(210,253):
            xy=(ix*.25,iy*.25);fp.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
            body=court(fp)
            if courts.intersects(body):continue
            if any(obs[pd.GetNetname()].intersects(sh)for pd in fp.Pads()for sh in r.polygons(pd,p.F_Cu)):continue
            candidates.append((math.dist(source,r.pos(r.pad('C40',1))),xy,angle))
assert candidates,'No reviewed free location adjacent to boost VIN'
distance,xy,angle=min(candidates)
fp.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])));fp.SetOrientationDegrees(angle)
print('Safe C40 candidate',xy,angle,'VIN pad distance',distance,flush=True)
try:
    r.route(('C40',1),('U9',4),width=.25,step=.025,bounds=(12,52,23,64))
    r.escapevia('new_C40_GND',('C40',2),diameter=.6,drill=.3,neck=.3)
finally:
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'exports/bypass-probe.kicad_pcb'),b)
    (root/'exports/bypass-candidate.json').write_text(json.dumps({'x':xy[0],'y':xy[1],'angle':angle,'vin_pad_distance_mm':distance},indent=2)+'\n',encoding='utf8')
print('Separate C40 bypass probe only; adopt after independent DRC')
