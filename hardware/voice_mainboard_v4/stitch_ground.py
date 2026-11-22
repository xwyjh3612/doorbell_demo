"""Add clearance-checked ground vias; keep RF/USB copper and antenna clear."""
from pathlib import Path
import sys,importlib.util,json,math
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
sys.argv=[__file__,str(file)]
spec=importlib.util.spec_from_file_location('r',ROOT.parent/'voice_mainboard_v3/route_helpers.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
from shapely.geometry import Point,Polygon,LineString
from shapely.ops import unary_union
previous=ROOT/'exports/ground-stitching.json'
if previous.exists():
    old=json.loads(previous.read_text(encoding='utf8'))
    old_points={tuple(xy)for xy in old['vias_mm']}
    held=[]
    for t in list(r.board.GetTracks()):
        if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND' and tuple(round(v,6)for v in r.pos(t)) in old_points:
            r.board.Remove(t);held.append(t)
    assert p.ZONE_FILLER(r.board).Fill(r.board.Zones())
obstacles=[]
for fp in r.board.GetFootprints():
    for pd in fp.Pads():
        for layer in [p.F_Cu,p.B_Cu]:
            if pd.IsOnLayer(layer):obstacles.extend(sh.buffer(.505)for sh in r.polygons(pd,layer))
for t in r.board.GetTracks():
    if isinstance(t,p.PCB_VIA):
        obstacles.append(Point(r.pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2+.505))
    elif t.GetNetname()!='GND':
        aa,zz=t.GetStart(),t.GetEnd()
        obstacles.append(LineString([(p.ToMM(aa.x),p.ToMM(aa.y)),(p.ToMM(zz.x),p.ToMM(zz.y))]).buffer(p.ToMM(t.GetWidth())/2+.505))
all_zones=[*r.board.Zones(),*[z for f in r.board.GetFootprints()for z in f.Zones()]]
for z in all_zones:
    if not z.GetIsRuleArea():continue
    outline=z.Outline()
    for n in range(outline.OutlineCount()):
        ring=outline.COutline(n)
        pts=[(p.ToMM(ring.CPoint(i).x),p.ToMM(ring.CPoint(i).y))for i in range(ring.PointCount())]
        if len(pts)>2:obstacles.append(Polygon(pts).buffer(.31))
blocked=unary_union(obstacles);added=[];regions={p.F_Cu:[],p.B_Cu:[]}
def polygon(ring):
    return [(p.ToMM(ring.CPoint(i).x),p.ToMM(ring.CPoint(i).y))for i in range(ring.PointCount())]
for z in r.board.Zones():
    if z.GetNetname()!='GND':continue
    q=z.GetFilledPolysList(z.GetLayer())
    for i in range(q.OutlineCount()):
        outer=polygon(q.COutline(i))
        if len(outer)<3:continue
        holes=[polygon(q.CHole(i,j))for j in range(q.HoleCount(i))]
        regions[z.GetLayer()].append(Polygon(outer,holes).buffer(0))
unions={layer:unary_union(parts)for layer,parts in regions.items()}
# One checked cross-layer connection per actual filled island, rather than a
# blanket via grid. Candidate center must lie in actual ground on both faces.
for layer in [p.F_Cu,p.B_Cu]:
    other=p.B_Cu if layer==p.F_Cu else p.F_Cu
    for island in regions[layer]:
        if any(island.contains(Point(xy))for xy in added):continue
        if any(island.contains(Point(r.pos(t))) and unions[other].contains(Point(r.pos(t)))
               for t in r.board.GetTracks() if isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND'):continue
        choices=island.intersection(unions[other]).difference(blocked).buffer(-.03)
        if choices.is_empty:continue
        pieces=list(choices.geoms)if hasattr(choices,'geoms')else[choices]
        shape=max(pieces,key=lambda s:s.area)
        if shape.area<.03:continue
        point=shape.representative_point();xy=(round(point.x,6),round(point.y,6))
        r.addvia('GND_STITCH'+str(len(added)),'GND',xy);added.append(xy)
        blocked=blocked.union(Point(xy).buffer(.805))
assert p.ZONE_FILLER(r.board).Fill(r.board.Zones());p.SaveBoard(str(file),r.board)
(ROOT/'exports/ground-stitching.json').write_text(json.dumps({'vias_mm':added,'diameter_mm':.6,'drill_mm':.3,'requires_native_DRC':True},indent=2)+'\n',encoding='utf8')
print('Added ground stitching vias:',len(added))
