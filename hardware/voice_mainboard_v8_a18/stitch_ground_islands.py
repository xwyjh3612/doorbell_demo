"""Stitch opposite-layer ground islands only when native DRC improves.

Use actual filled polygons to find a via location. Never bridge an intervening
signal trace, alter pad nets, or remove existing copper to obtain a pass.
"""
import datetime
import json
import math
import shutil
import subprocess
from pathlib import Path

from comparison_route_geometry import b, FILE, p, pos, polys, layers
from repair_comparison_groups import groups
from local_escape_review import obstruction
import local_escape_review as escape_geometry
from shapely.geometry import Polygon, Point

out = FILE.parent/'exports'
snapshot = FILE.parent/'iterations'/('ground-stitch-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE, snapshot/FILE.name)
cli = Path(__file__).resolve().parents[2]/'build/cad-tools/kicad/bin/kicad-cli.exe'
held = []
log = []

def check():
    b.BuildConnectivity()
    assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(FILE), b)
    subprocess.run([str(cli), 'pcb', 'drc', '--format', 'json', '--output', str(out/'ground-stitch-drc.json'), str(FILE)], check=True, capture_output=True)
    return json.loads((out/'ground-stitch-drc.json').read_text(encoding='utf-8'))

def hard(report):
    return sum(q['type'] not in ['track_dangling', 'via_dangling'] for q in report['violations'])

def island_shapes():
    result = []
    for z in b.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != 'GND':
            continue
        s = z.GetFilledPolysList(z.GetLayer())
        for i in range(s.OutlineCount()):
            q = s.COutline(i)
            holes = []
            for k in range(s.HoleCount(i)):
                h = s.CHole(i, k)
                holes.append([(p.ToMM(h.CPoint(j).x), p.ToMM(h.CPoint(j).y)) for j in range(h.PointCount())])
            shape = Polygon([(p.ToMM(q.CPoint(j).x), p.ToMM(q.CPoint(j).y)) for j in range(q.PointCount())], holes).buffer(0)
            result.append((z.GetLayer(), shape))
    return result

def touches(shape, layer, objects):
    for q in objects:
        if not q.IsOnLayer(layer):
            continue
        shapes = polys(q, layer) if isinstance(q, p.PAD) else [Point(pos(q)).buffer(p.ToMM(q.GetWidth(layer))/2)]
        if any(shape.intersection(s).area > 1e-8 for s in shapes):
            return True
    return False

report = check()
assert hard(report) == 0
for iteration in range(8):
    escape_geometry.dynamic_index = None
    gs = groups('GND', exclude_point_contacts=True)
    if len(gs) < 2:
        break
    main = max(gs, key=len)
    islands = island_shapes()
    candidates = []
    for g in gs:
        if g is main:
            continue
        source = [(l,s) for l,s in islands if touches(s,l,g)]
        goal = [(l,s) for l,s in islands if touches(s,l,main)]
        for sl, a in source:
            for zl, z in goal:
                if sl == zl:
                    continue
                # Require useful copper contact, not a zero-area tangent.
                common = a.buffer(.12).intersection(z.buffer(.12))
                if common.is_empty:
                    continue
                lo_x, lo_y, hi_x, hi_y = common.bounds
                if (hi_x-lo_x)*(hi_y-lo_y) > 80:
                    continue
                points = [common.representative_point()]
                for ix in range(math.ceil(lo_x*20), math.floor(hi_x*20)+1):
                    for iy in range(math.ceil(lo_y*20), math.floor(hi_y*20)+1):
                        q = Point(ix/20,iy/20)
                        if common.covers(q):
                            points.append(q)
                for q in points:
                    xy = (q.x,q.y)
                    if obstruction('GND',xy,xy,p.F_Cu):
                        continue
                    candidates.append((min(math.dist(xy,pos(t)) for t in g),xy))
    accepted = False
    tried = set()
    for _, xy in sorted(candidates)[:40]:
        key = tuple(round(q,4) for q in xy)
        if key in tried:
            continue
        tried.add(key)
        v = p.PCB_VIA(b)
        v.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
        v.SetWidth(p.FromMM(.45)); v.SetDrill(p.FromMM(.2))
        v.SetViaType(p.VIATYPE_THROUGH); v.SetLayerPair(p.F_Cu,p.B_Cu)
        v.SetNetCode(b.FindNet('GND').GetNetCode()); b.Add(v)
        candidate = check()
        good = hard(candidate) == 0 and len(candidate['unconnected_items']) < len(report['unconnected_items'])
        log.append({'via_mm':xy,'accepted':good,'native_unconnected_before':len(report['unconnected_items']),'native_unconnected_after':len(candidate['unconnected_items'])})
        if good:
            report = candidate
            accepted = True
            print('Stitched ground:',xy,'native unconnected:',len(report['unconnected_items']),flush=True)
            break
        b.Remove(v); held.append(v)
        b.BuildConnectivity(); assert p.ZONE_FILLER(b).Fill(b.Zones())
    if not accepted:
        break
report = check()
(out/'ground-stitch-review.json').write_text(json.dumps({'trials':log,'native_unconnected':len(report['unconnected_items']),'scope':'Accepted only after a reduction in native unconnected items with no hard DRC violations.'},indent=2),encoding='utf-8')
for q in held:
    q.thisown = False
print('Ground stitch review finished:',len(report['unconnected_items']),flush=True)
