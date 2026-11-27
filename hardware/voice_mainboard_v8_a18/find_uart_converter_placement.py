"""Find a legal U4 position with clear, conventional off-pad signal vias.

Search actual copper geometry before moving a part; retain every existing
track, pad and rule. Native DRC is the final authority. Power and signal
connections must subsequently be restored before accepting the trial.
"""
import json
import math
import os
import shutil
from pathlib import Path
import subprocess

from comparison_route_geometry import b, FILE, p, pos, polys, layers, outline, rules, required_clearance
import numpy as np
from shapely.geometry import Point, LineString, Polygon
from shapely.strtree import STRtree

ref = os.environ.get('A18_PLACEMENT_REF', 'U4')
f = next(f for f in b.GetFootprints() if f.GetReference() == ref)
signal_numbers = os.environ.get('A18_PLACEMENT_SIGNAL_PADS', '3,4').split(',')
signal_goals = json.loads(os.environ.get('A18_PLACEMENT_SIGNAL_GOALS', '{"3":[20.44,43.75],"4":[54.5,33.45]}'))
via_diameter = float(os.environ.get('A18_PLACEMENT_VIA_DIAMETER_MM', '.45'))
neck_width = float(os.environ.get('A18_PLACEMENT_NECK_WIDTH_MM', '.16'))
assert via_diameter >= .4 and neck_width >= .12
original = (f.GetPosition(), f.GetOrientationDegrees(), f.GetLayer())
requested_side = os.environ.get('A18_PLACEMENT_SIDE')
if requested_side and f.GetLayer() != (p.F_Cu if requested_side == 'F' else p.B_Cu):
    f.Flip(f.GetPosition(), False)
objects = []
shapes = []
for other in b.GetFootprints():
    if other == f:
        continue
    for d in other.Pads():
        for layer in layers:
            if d.IsOnLayer(layer):
                for sh in polys(d, layer):
                    objects.append((d.GetNetname(), layer, True, d))
                    shapes.append(sh)
for t in b.GetTracks():
    sh = (Point(pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu)) / 2) if isinstance(t, p.PCB_VIA)
          else LineString([(p.ToMM(q.x), p.ToMM(q.y)) for q in (t.GetStart(), t.GetEnd())]).buffer(p.ToMM(t.GetWidth()) / 2))
    for layer in layers:
        if t.IsOnLayer(layer):
            objects.append((t.GetNetname(), layer, False, t))
            shapes.append(sh)
tree = STRtree(shapes)
holes = [(Point(pos(t)), p.ToMM(t.GetDrill()) / 2) for t in b.GetTracks() if isinstance(t, p.PCB_VIA)]
holes += [(Point(pos(d)), p.ToMM(d.GetDrillSize().x) / 2) for other in b.GetFootprints()
          if other != f for d in other.Pads() if d.GetDrillSize().x]
hole_shapes = [q.buffer(r + .351) for q, r in holes]
hole_tree = STRtree(hole_shapes)
reach_maps = {}
for number,path in json.loads(os.environ.get('A18_CONVERTER_REACH_MAPS', '{}')).items():
    # NpzFile re-decompresses an array on every [] access. Materialize each
    # immutable diagnostic once, rather than rereading millions of cells for
    # every candidate point.
    with np.load(path) as field:
        reach_maps[number]={k:field[k] for k in ('xs','ys','reachable')}

def courtyards(footprint):
    footprint.BuildCourtyardCaches()
    shape = footprint.GetCourtyard(footprint.GetLayer())
    return [Polygon([(p.ToMM(q.CPoint(i).x), p.ToMM(q.CPoint(i).y))
                     for i in range(q.PointCount())])
            for q in [shape.COutline(k) for k in range(shape.OutlineCount())]
            if q.PointCount() >= 3]

other_courtyards = [sh for other in b.GetFootprints() if other != f and other.GetLayer() == f.GetLayer()
                    for sh in courtyards(other)]

def reachable_escape(number, xy, layer=None):
    if number not in reach_maps:
        return True
    field = reach_maps[number]
    ix = round((xy[0]-field['xs'][0])/(field['xs'][1]-field['xs'][0]))
    iy = round((xy[1]-field['ys'][0])/(field['ys'][1]-field['ys'][0]))
    if not (0<=ix<len(field['xs']) and 0<=iy<len(field['ys'])):
        return False
    if layer is not None:
        return bool(field['reachable'][layers.index(layer),iy,ix])
    return bool(field['reachable'][:, iy, ix].any())

def blocked(sh, net, layer, margin=0, via=False):
    for i in tree.query(sh.buffer(.5)):
        name, l, ispad, _ = objects[int(i)]
        if not via and l != layer:
            continue
        distance = shapes[int(i)].distance(sh)
        if via and ispad and distance < via_diameter/2+.05:
            return True
        if name != net and distance < required_clearance(net, name) + margin:
            return True
    return False

def legal_pads():
    for d in f.Pads():
        # PTH headers occupy both copper layers. Screening only the mounting
        # side wastes native trials on antenna keepouts and back-side copper.
        for layer in layers:
            if not d.IsOnLayer(layer):
                continue
            for sh in polys(d, layer):
                if not outline.buffer(-.501).covers(sh) or blocked(sh, d.GetNetname(), layer):
                    return False
                if any(z.IsOnLayer(layer) and z.GetDoNotAllowPads() and area.intersects(sh)
                       for z, area in rules):
                    return False
                for i in hole_tree.query(sh):
                    pt, radius = holes[int(i)]
                    if sh.distance(pt) < radius + .251:
                        return False
    for sh in courtyards(f):
        if any(sh.intersection(other).area > 1e-9 for other in other_courtyards):
            return False
        if any(z.IsOnLayer(f.GetLayer()) and z.GetDoNotAllowFootprints() and area.intersects(sh)
               for z, area in rules):
            return False
    return True

def escape(d, previous):
    start = pos(d)
    if (os.environ.get('A18_PLACEMENT_DIRECT_FIELD_ENDPOINTS')=='1'
            and d.GetNumber() in reach_maps and reachable_escape(d.GetNumber(),start,f.GetLayer())):
        # A directly reachable SMT land does not need a redundant off-pad via.
        # Require the actual mounting layer, not same XY on the opposite face.
        return start
    # A plated header pad is already a through-layer anchor. Requiring an
    # additional nearby via rejects usable header positions unnecessarily.
    if d.GetDrillSize().x and all(d.IsOnLayer(layer) for layer in layers):
        return start if reachable_escape(d.GetNumber(), start) else None
    own = [(q, polys(q, f.GetLayer())) for q in f.Pads()]
    for radius in (.8, 1.2, 1.6):
        for angle in range(0, 360, 45):
            xy = (start[0] + radius * math.cos(math.radians(angle)), start[1] + radius * math.sin(math.radians(angle)))
            pt = Point(xy)
            line = LineString([start, xy])
            if not reachable_escape(d.GetNumber(), xy):
                continue
            if any(math.dist(xy, q) < .451 for q in previous):
                continue
            if not outline.buffer(-via_diameter/2-.501).covers(pt) or blocked(pt, d.GetNetname(), f.GetLayer(), via_diameter/2, via=True):
                continue
            if any(hole_shapes[int(i)].intersects(pt) for i in hole_tree.query(pt)):
                continue
            if blocked(line, d.GetNetname(), f.GetLayer(), neck_width/2):
                continue
            if any(pt.distance(sh) < (via_diameter/2+.05 if q==d else via_diameter/2+required_clearance(d.GetNetname(),q.GetNetname()))
                   or (q != d and line.distance(sh) < required_clearance(d.GetNetname(),q.GetNetname())+neck_width/2)
                   for q, ss in own for sh in ss):
                continue
            if any((z.GetDoNotAllowVias() and sh.buffer(via_diameter/2+.011).intersects(pt))
                   or (z.IsOnLayer(f.GetLayer()) and z.GetDoNotAllowTracks() and sh.buffer(neck_width/2+.011).intersects(line))
                   for z, sh in rules):
                continue
            return xy
    return None

candidates = []
radial_offsets=[(radius*math.cos(math.radians(a)),radius*math.sin(math.radians(a)))
                for radius in (.8,1.2,1.6) for a in range(0,360,45)]
position_step = float(os.environ.get('A18_CONVERTER_POSITION_STEP', '1'))
for angle in tuple(float(q)for q in os.environ.get('A18_PLACEMENT_ANGLES','90,0,180,270').split(',')):
    f.SetOrientationDegrees(angle)
    for x in np.arange(float(os.environ.get('A18_CONVERTER_X_MIN', '29')), float(os.environ.get('A18_CONVERTER_X_MAX', '46')) + position_step / 2, position_step):
        for y in np.arange(float(os.environ.get('A18_CONVERTER_Y_MIN', '12')), float(os.environ.get('A18_CONVERTER_Y_MAX', '30')) + position_step / 2, position_step):
            x, y = float(x), float(y)
            f.SetPosition(p.VECTOR2I(p.FromMM(x), p.FromMM(y)))
            signal_pads = [d for d in f.Pads() if d.GetNumber() in signal_numbers]
            # Exact same radial candidates used by escape(), screened against
            # the read-only field first. This avoids costly full geometry work
            # on positions which cannot have a reachable pad/escape at all.
            if any(d.GetNumber() in reach_maps and not any(reachable_escape(d.GetNumber(),
                    (pos(d)[0]+dx,pos(d)[1]+dy)) for dx,dy in ([(0,0)] if d.GetDrillSize().x else ([(0,0)]+radial_offsets if os.environ.get('A18_PLACEMENT_DIRECT_FIELD_ENDPOINTS')=='1' else radial_offsets)))
                   for d in signal_pads):
                continue
            if not legal_pads():
                continue
            escapes = {}
            for d in signal_pads:
                xy = escape(d, list(escapes.values()))
                if xy is None:
                    break
                escapes[d.GetNumber()] = xy
            if len(escapes) != len(signal_numbers):
                continue
            score = sum(math.dist(escapes[number], signal_goals[number]) for number in signal_numbers)
            candidates.append({'x': x, 'y': y, 'angle': angle, 'escapes': escapes, 'score': score})
    print('Placement angle',angle,'reachable legal candidates',len(candidates),flush=True)
repo = Path(__file__).resolve().parents[2]
cli = repo / 'build/cad-tools/kicad/bin/kicad-cli.exe'
before_file = FILE.parent / 'exports/placement-search-before.kicad_pcb'
f.SetPosition(original[0]); f.SetOrientationDegrees(original[1])
shutil.copy2(FILE, before_file)
selected = None
trials = []
for candidate in sorted(candidates, key=lambda q: q['score'])[:int(os.environ.get('A18_PLACEMENT_NATIVE_TRIAL_LIMIT', '12'))]:
    f.SetPosition(p.VECTOR2I(p.FromMM(candidate['x']), p.FromMM(candidate['y'])))
    f.SetOrientationDegrees(candidate['angle'])
    b.BuildConnectivity(); assert p.ZONE_FILLER(b).Fill(b.Zones()); p.SaveBoard(str(FILE), b)
    report_file = FILE.parent / 'exports/placement-search-native.json'
    subprocess.run([str(cli), 'pcb', 'drc', '--format', 'json', '--output', str(report_file), str(FILE)], check=True, capture_output=True)
    report = json.loads(report_file.read_text(encoding='utf-8'))
    hard = [q for q in report['violations'] if q['type'] not in ('track_dangling', 'via_dangling')]
    trials.append({'position': candidate, 'hard': hard})
    if not hard:
        selected = candidate
        design = json.loads((FILE.parent / 'design.json').read_text(encoding='utf-8'))
        for q in design['parts']:
            if q['ref'] == ref:
                q.update(x=candidate['x'], y=candidate['y'], angle=candidate['angle'], side='F' if f.GetLayer() == p.F_Cu else 'B')
        (FILE.parent / 'design.json').write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding='utf-8')
        break
if selected is None:
    if f.GetLayer() != original[2]:
        f.Flip(f.GetPosition(), False)
    f.SetPosition(original[0]); f.SetOrientationDegrees(original[1])
    b.BuildConnectivity(); assert p.ZONE_FILLER(b).Fill(b.Zones()); p.SaveBoard(str(FILE), b)
(FILE.parent / 'exports/placement-search.json').write_text(json.dumps({'reference': ref, 'geometrically_legal_candidates': len(candidates), 'selected': selected, 'trials': trials,
    'signal_reachability_maps': sorted(reach_maps)}, indent=2), encoding='utf-8')
print(json.dumps({'geometrically_legal_candidates': len(candidates), 'selected': selected}, indent=2), flush=True)
