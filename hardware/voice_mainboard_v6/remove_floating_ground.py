"""Remove copper/vias in ground components with no physical component pad.

Connectivity is checked independently as a two-layer polygon graph; no pad is
deleted and all board checks must run again after this cleanup.
"""
from pathlib import Path
import sys,json,pcbnew as p
from route_support import load
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
r=load();b=r.board;layers=[p.F_Cu,p.B_Cu];regions=[]
for layer in layers:
    shapes=[]
    for z in b.Zones():
        if z.GetIsRuleArea() or z.GetNetname()!='GND' or z.GetLayer()!=layer:continue
        ps=z.GetFilledPolysList(layer)
        for i in range(ps.OutlineCount()):
            ch=ps.COutline(i);shapes.append(Polygon([(p.ToMM(ch.CPoint(j).x),p.ToMM(ch.CPoint(j).y)) for j in range(ch.PointCount())]).buffer(0))
    for f in b.GetFootprints():
        for pd in f.Pads():
            if pd.GetNetname()=='GND' and pd.IsOnLayer(layer):shapes.extend(r.polygons(pd,layer))
    for t in b.GetTracks():
        if t.GetNetname()!='GND':continue
        if isinstance(t,p.PCB_VIA):shapes.append(Point(r.pos(t)).buffer(p.ToMM(t.GetWidth(layer))/2))
        elif t.GetLayer()==layer:shapes.append(LineString([r.pos(t),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2))
    merged=unary_union(shapes);regions.extend((layer,q) for q in (list(merged.geoms) if hasattr(merged,'geoms') else [merged]))
parents=list(range(len(regions)))
def root(i):
    while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
    return i
def locate(xy,layer):return next((i for i,(la,q) in enumerate(regions) if la==layer and q.buffer(.00001).covers(Point(xy))),None)
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND':
        ids=[locate(r.pos(t),la) for la in layers]
        if all(i is not None for i in ids):parents[root(ids[1])]=root(ids[0])
anchored=set()
for f in b.GetFootprints():
    for pd in f.Pads():
        if pd.GetNetname()!='GND':continue
        for la in layers:
            if pd.IsOnLayer(la):
                i=locate(r.pos(pd),la)
                if i is not None:anchored.add(root(i))
floating={i for i in range(len(regions)) if root(i) not in anchored};held=[];removed=[]
for t in list(b.GetTracks()):
    if t.GetNetname()!='GND':continue
    la=p.F_Cu if isinstance(t,p.PCB_VIA) else t.GetLayer();i=locate(r.pos(t),la)
    if i in floating:removed.append(t.m_Uuid.AsString());held.append(t);b.Remove(t)
for z in b.Zones():
    if not z.GetIsRuleArea() and z.GetNetname()=='GND':z.SetMinThickness(p.FromMM(.25))
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
(ROOT/'exports/floating-ground-cleanup.json').write_text(json.dumps({'layer_components':len(regions),'unanchored_layer_components':len(floating),'removed_copper_uuids':removed,'physical_component_pads_removed':0},indent=2)+'\n',encoding='utf8')
print('Floating copper removed',len(removed),'from',len(floating),'unanchored ground areas')
