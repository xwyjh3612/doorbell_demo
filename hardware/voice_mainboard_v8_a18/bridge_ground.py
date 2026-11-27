"""Bridge overlapping ground islands with ordinary off-pad through vias.

Uses filled copper geometry, never zone origins. KiCad DRC must be rerun.
"""
from pathlib import Path
import json, sys, os
import pcbnew as p
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO/'build/cad-tools/route-python'))
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
if os.environ.get('A18_REPAIR_BOARD'):
    from comparison_route_geometry import b,FILE,pos,polys,rules,outline,layers,required_clearance
    ROOT=FILE.parent
else:
    from repair_connections import b,FILE,pos,polys,rules,outline
    layers=[p.F_Cu,p.B_Cu]
diameter=float(os.environ.get('A18_GROUND_VIA_MM','.6'))
drill=float(os.environ.get('A18_GROUND_DRILL_MM','.3'))
assert diameter>=drill+.2, 'Keep at least 0.1mm annular ring'
radius=diameter/2

regions=[]
for zone in b.Zones():
    if zone.GetIsRuleArea()or zone.GetNetname()!='GND':continue
    layer=zone.GetLayer();shape=zone.GetFilledPolysList(layer)
    for i in range(shape.OutlineCount()):
        q=shape.COutline(i)
        sh=Polygon([(p.ToMM(q.CPoint(j).x),p.ToMM(q.CPoint(j).y))for j in range(q.PointCount())])
        holes=[]
        for k in range(shape.HoleCount(i)):
            h=shape.CHole(i,k)
            holes.append([(p.ToMM(h.CPoint(j).x),p.ToMM(h.CPoint(j).y))for j in range(h.PointCount())])
        sh=Polygon(sh.exterior.coords,holes).buffer(0)
        if sh.area>.01:regions.append((layer,sh))
obstacles=[]
for f in b.GetFootprints():
    for d in f.Pads():
        for layer in layers:
            if d.IsOnLayer(layer):obstacles.extend(sh.buffer(radius+.05 if d.GetNetname()=='GND'else radius+(required_clearance('GND',d.GetNetname())+.01 if os.environ.get('A18_REPAIR_BOARD')else .211))for sh in polys(d,layer))
        if d.GetDrillSize().x:obstacles.append(Point(pos(d)).buffer(p.ToMM(d.GetDrillSize().x)/2+.555))
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):
        obstacles.append(Point(pos(t)).buffer(.555 if t.GetNetname()=='GND'else p.ToMM(t.GetWidth(p.F_Cu))/2+radius+(required_clearance('GND',t.GetNetname())+.01 if os.environ.get('A18_REPAIR_BOARD')else .211)))
    elif t.GetNetname()!='GND':
        a,z=t.GetStart(),t.GetEnd()
        obstacles.append(LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]).buffer(p.ToMM(t.GetWidth())/2+radius+(required_clearance('GND',t.GetNetname())+.01 if os.environ.get('A18_REPAIR_BOARD')else .211)))
for z,sh in rules:
    if z.GetDoNotAllowVias():obstacles.append(sh.buffer(radius+.011))
blocked=unary_union(obstacles)
parent=list(range(len(regions)))
def find(x):
    while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
    return x
def join(a,z):parent[find(a)]=find(z)
crossings=[t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND']
crossings += [d for f in b.GetFootprints()for d in f.Pads()if d.GetAttribute()==p.PAD_ATTRIB_PTH and d.GetNetname()=='GND']
for t in crossings:
    ids=[i for i,(_,sh)in enumerate(regions)if sh.distance(Point(pos(t)))<.3]
    for i in ids[1:]:join(ids[0],i)
added=[]
for i,(la,a)in enumerate(regions):
    for j,(lz,z)in enumerate(regions):
        if la==lz or find(i)==find(j):continue
        common=a.intersection(z).buffer(-radius-.01).difference(blocked)
        if common.is_empty:continue
        pieces=[common]if common.geom_type=='Polygon'else[g for g in common.geoms if g.geom_type=='Polygon']
        if not pieces:continue
        sh=max(pieces,key=lambda q:q.area);point=sh.representative_point();xy=(point.x,point.y)
        v=p.PCB_VIA(b);v.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
        v.SetWidth(p.FromMM(diameter));v.SetDrill(p.FromMM(drill));v.SetViaType(p.VIATYPE_THROUGH)
        v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNetCode(b.FindNet('GND').GetNetCode());b.Add(v)
        blocked=blocked.union(point.buffer(.555));join(i,j)
        added.append({'position_mm':xy,'regions':[i,j]})
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
report={'filled_ground_regions_before':len(regions),'added_off_pad_vias':added,'via_diameter_mm':diameter,'via_drill_mm':drill,
        'region_graph_components_before_refill':len({find(i)for i in range(len(regions))}),
        'requires_fresh_native_DRC':True,'manufacturing_ready':False}
(ROOT/'exports/ground-island-bridges.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Ground islands',len(regions),'bridging vias',len(added),'remaining region groups',report['region_graph_components_before_refill'])
