"""Place one explicitly requested part against actual courtyards and copper.

Use bounded local search, retain full footprints and retire only incident
routes. This tool is not an autorouter or a substitute for native DRC.
"""
from pathlib import Path
import collections, datetime, json, math, os, shutil
import pcbnew as p
from comparison_route_geometry import b, FILE, pos, polys, outline
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree
from shapely.affinity import rotate
from route_net_classes import PROTECTED

ref = os.environ['A18_MOVE_REF']
target = [float(q) for q in os.environ['A18_MOVE_TARGET'].split(',')]
fps = {f.GetReference():f for f in b.GetFootprints()}
f = fps[ref]
prerequisites=json.loads(os.environ.get('A18_MOVE_PREREQUISITES','[]'))
assert all(q['ref']!=ref for q in prerequisites)
changed_refs={ref,*[q['ref'] for q in prerequisites]}
oldpoints={(d.GetPosition().x,d.GetPosition().y) for name in changed_refs for d in fps[name].Pads()}
OUT = FILE.parent
snapshot = OUT/'iterations'/('before-local-part-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
snapshot.mkdir(parents=True)
for name in [FILE.name,'design.json']:
    shutil.copy2(OUT/name,snapshot/name)
for q in prerequisites:
    other=fps[q['ref']]
    wanted=p.F_Cu if q['side']=='F' else p.B_Cu
    if other.GetLayer()!=wanted:other.Flip(other.GetPosition(),False)
    other.SetOrientationDegrees(q['angle'])
    other.SetPosition(p.VECTOR2I(p.FromMM(q['x']),p.FromMM(q['y'])))
if os.environ.get('A18_MOVE_SIDE') in ['F','B']:
    wanted=p.F_Cu if os.environ['A18_MOVE_SIDE']=='F' else p.B_Cu
    if f.GetLayer()!=wanted:f.Flip(f.GetPosition(),False)
layer = f.GetLayer()
if os.environ.get('A18_MOVE_ANGLE'):
    f.SetOrientationDegrees(float(os.environ['A18_MOVE_ANGLE']))
def court(fp):
    lines, circles = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() not in [p.F_CrtYd,p.B_CrtYd]:
            continue
        if g.GetShape()==p.S_SEGMENT:
            lines.append(LineString([(p.ToMM(g.GetStart().x),p.ToMM(g.GetStart().y)),(p.ToMM(g.GetEnd().x),p.ToMM(g.GetEnd().y))]))
        elif g.GetShape()==p.S_CIRCLE:
            circles.append(Point(p.ToMM(g.GetStart().x),p.ToMM(g.GetStart().y)).buffer(math.hypot(p.ToMM(g.GetStart().x-g.GetEnd().x),p.ToMM(g.GetStart().y-g.GetEnd().y))))
        elif g.GetShape()==p.S_RECT:
            a,z=g.GetStart(),g.GetEnd()
            circles.append(box(min(p.ToMM(a.x),p.ToMM(z.x)),min(p.ToMM(a.y),p.ToMM(z.y)),max(p.ToMM(a.x),p.ToMM(z.x)),max(p.ToMM(a.y),p.ToMM(z.y))))
        elif g.GetShape()==p.S_POLYGON:
            shape=g.GetPolyShape()
            for i in range(shape.OutlineCount()):
                q=shape.COutline(i)
                circles.append(Polygon([(p.ToMM(q.CPoint(j).x),p.ToMM(q.CPoint(j).y)) for j in range(q.PointCount())]))
    return unary_union([*polygonize(lines),*circles])
occupied=unary_union([court(fp).buffer(.08) for fp in fps.values() if fp!=f and fp.GetLayer()==layer])
# Opposite-side through-hole leads still protrude through this face. A
# courtyard-only comparison by mounting side would otherwise permit an SMT
# body to cover the jack's blade terminals after moving the jack to the back.
if not any(d.GetDrillSize().x for d in f.Pads()):
    leads=[]
    for fp in fps.values():
        if fp==f:continue
        for d in fp.Pads():
            size=d.GetDrillSize()
            if not size.x:continue
            x,y=pos(d);w,h=p.ToMM(size.x),p.ToMM(size.y)
            lead=rotate(box(x-w/2,y-h/2,x+w/2,y+h/2),d.GetOrientationDegrees(),origin=(x,y))
            leads.append(lead.buffer(.4))
    occupied=unary_union([occupied,*leads])
for q in prerequisites:
    other=fps[q['ref']];sh=court(other)
    if q['ref']=='J1' and os.environ.get('A18_ALLOW_JACK_BODY_OVERHANG')=='1':
        # Connector plastic may project beyond the PCB; all blade pads remain
        # inside the unchanged copper-edge margin. The provisional A18 inner
        # wall is at x=77mm in board coordinates (2mm wall assumption).
        assert sh.bounds[0]>=.5 and sh.bounds[2]<=77 and sh.bounds[1]>=.5 and sh.bounds[3]<=72.5
        assert all(outline.buffer(-.5).covers(shape) for d in other.Pads()
                   for shape in polys(d,p.F_Cu)), 'Jack metal pads exceed board margin'
    else:
        assert outline.buffer(-.5).covers(sh),q['ref']+' courtyard exceeds board margin'
    peers=unary_union([court(fp).buffer(.08) for fp in fps.values()
                      if fp.GetReference() not in changed_refs and fp.GetLayer()==other.GetLayer()])
    overlaps=[fp.GetReference() for fp in fps.values() if fp.GetReference() not in changed_refs
              and fp.GetLayer()==other.GetLayer() and court(fp).buffer(.08).intersects(sh)]
    assert not overlaps,q['ref']+' overlaps unmoved courtyards '+str(overlaps)
held, removed=[],[]
for t in list(b.GetTracks()):
    if any((q.x,q.y) in oldpoints for q in [t.GetStart(),t.GetEnd()]):
        held.append(t)
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()})
        b.Remove(t)
obstacles=[]
for fp in fps.values():
    if fp==f:
        continue
    for d in fp.Pads():
        if d.IsOnLayer(layer):
            obstacles.extend((d.GetNetname(),sh,None) for sh in polys(d,layer))
for t in b.GetTracks():
    if not t.IsOnLayer(layer):
        continue
    shape=Point(pos(t)).buffer(p.ToMM(t.GetWidth(layer))/2) if isinstance(t,p.PCB_VIA) else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2)
    obstacles.append((t.GetNetname(),shape,t))
obstacle_tree=STRtree([q[1] for q in obstacles])
allowed_outline=outline.buffer(-.5)
found=None
retire=[]
reasons=collections.Counter();blocked_nets=collections.Counter()
for x,y in sorted(((target[0]+dx*.25,target[1]+dy*.25) for dx in range(-20,21) for dy in range(-20,21)),key=lambda q:math.dist(q,target)):
    f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
    sh=court(f)
    if occupied.intersects(sh):
        reasons['courtyard overlap']+=1
        continue
    if not allowed_outline.covers(sh):
        reasons['courtyard outside edge margin']+=1
        continue
    hits=[];blocked=False
    for d in f.Pads():
        for own in polys(d,layer):
            # Keep the same exact distance checks, but query only nearby
            # geometry rather than every trace for every placement point.
            for index in obstacle_tree.query(own.buffer(.202)):
                net,shape,obj=obstacles[int(index)]
                collision=(d.GetNetname()!=net and own.distance(shape)<.201) or (obj is not None and isinstance(obj,p.PCB_VIA) and own.distance(shape)<.051)
                if not collision:
                    continue
                if (obj is not None and not obj.IsLocked()
                    and net not in PROTECTED
                    and os.environ.get('A18_MOVE_RIPUP')=='1'):
                    hits.append(obj)
                else:
                    blocked=True
                    blocked_nets[net]+=1
    if blocked:
        reasons['pad copper or via clearance']+=1
        continue
    found=(x,y)
    retire=hits
    break
if found is None:
    diagnostic={'ref':ref,'target':target,'side':os.environ.get('A18_MOVE_SIDE'),'angle':f.GetOrientationDegrees(),
                'rejections':dict(reasons),'blocking_nets':dict(blocked_nets)}
    (OUT/'exports/local-placement-rejections.json').write_text(json.dumps(diagnostic,indent=2),encoding='utf-8')
    print(json.dumps(diagnostic),flush=True)
    for t in held:
        t.thisown=False
    raise RuntimeError('No valid local placement; saved PCB not changed')
for t in {q.m_Uuid.AsString():q for q in retire}.values():
    held.append(t)
    removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'reason':'local-capacitor-copper-clearance'})
    b.Remove(t)
data=json.loads((OUT/'design.json').read_text(encoding='utf-8'))
for q in data['parts']:
    if q['ref'] in changed_refs:
        changed=fps[q['ref']]
        q.update(x=pos(changed)[0],y=pos(changed)[1],angle=changed.GetOrientationDegrees(),side='F' if changed.GetLayer()==p.F_Cu else 'B')
data['two_layer_iterations'].append({'snapshot':str(snapshot.relative_to(OUT)),'reason':'Local placement checked against routed copper','move':{'ref':ref,'actual_mm':found},'prerequisites':prerequisites})
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE),b)
(OUT/'exports/local-part-copper-placement.json').write_text(json.dumps({'ref':ref,'target':target,'actual_mm':found,'removed':removed},indent=2),encoding='utf-8')
for t in held:
    t.thisown=False
print('Placed',ref,'at',found,'with native DRC required.')
