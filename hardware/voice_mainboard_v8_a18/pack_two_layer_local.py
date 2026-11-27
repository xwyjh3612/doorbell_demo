"""Resolve local courtyard/pad collisions without shrinking real footprints.

Only the explicitly listed parts may move; retain full manufacturer pad
geometry and cross-layer PTH clearance. Native DRC is the acceptance check.
"""
from pathlib import Path
import json, math, sys
import pcbnew as p
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / 'build/cad-tools/route-python'))
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
OUT = ROOT / 'two_layer_work'; FILE = OUT / 'voice_mainboard_a18_2layer.kicad_pcb'
b = p.LoadBoard(str(FILE)); fps = {f.GetReference(): f for f in b.GetFootprints()}
data = json.loads((OUT / 'design.json').read_text(encoding='utf-8'))
outline = Polygon(data['mechanical']['outline_mm']).buffer(-.5)
def xy(v): return p.ToMM(v.x), p.ToMM(v.y)
def court(f):
    lines = []; circles = []
    for g in f.GraphicalItems():
        if g.GetLayer() not in [p.F_CrtYd, p.B_CrtYd]: continue
        if g.GetShape() == p.S_SEGMENT: lines.append(LineString([xy(g.GetStart()), xy(g.GetEnd())]))
        elif g.GetShape() == p.S_CIRCLE: circles.append(Point(xy(g.GetStart())).buffer(math.dist(xy(g.GetStart()), xy(g.GetEnd()))))
    polys = list(polygonize(lines)) + circles
    if not polys:
        for d in f.Pads():
            x,y = xy(d.GetPosition()); sx,sy = xy(d.GetSize())
            polys.append(box(x-sx/2-.25,y-sy/2-.25,x+sx/2+.25,y+sy/2+.25))
    return unary_union(polys)
def copper(d, layer):
    sh = d.GetEffectivePolygon(layer)
    return unary_union([Polygon([xy(r.CPoint(j)) for j in range(r.PointCount())])
                        for r in [sh.COutline(i) for i in range(sh.OutlineCount())] if r.PointCount() >= 3])
targets = {
    'F1': (66,25,90,'B'), 'C5': (57,5.5,0,'B'),
    'U3': (52,35.5,90,'B'), 'U4': (56.5,35.5,90,'B'), 'U5': (60,32,90,'B'),
    'Q2': (47,35,180,'B'), 'U14': (35,49,0,'F'),
    'R70': (62,40,0,'B'),
    'C13': (50,38.5,0,'B'), 'C14': (53,31,0,'B'),
    'C15': (62,35.5,0,'B'), 'C16': (62,28.5,90,'B'),
    'C17': (67,33.5,0,'B'), 'C18': (67,31,0,'B'),
    'C19': (46,32,90,'B'), 'R8': (44,35,90,'B'),
    'C61': (31.5,51.5,90,'F'), 'C62': (35,52.5,0,'F'),
    'R75': (39.5,48.5,0,'F'), 'R76': (39,52,0,'F'),
    'R26': (65.5,32,0,'F'), 'R27': (65.5,34,0,'F'),
    'R28': (47.5,46.5,0,'F'), 'R29': (50.5,46,0,'F'),
    'R30': (66.5,29,0,'F'),
    'C65': (34.8,44,90,'B'),
}
placed = {ref for ref in fps if ref not in targets}
entries = []
for ref,(tx,ty,angle,side) in targets.items():
    f = fps[ref]; target_layer = p.B_Cu if side == 'B' else p.F_Cu
    if f.GetLayer() != target_layer: f.Flip(f.GetPosition(), False)
    f.SetOrientationDegrees(angle)
    same_side = unary_union([court(fps[r]).buffer(.08) for r in placed if fps[r].GetLayer() == target_layer])
    # Opposite-side through pads occupy both copper sides and require space.
    through = unary_union([copper(d,target_layer).buffer(.201) for r in placed for d in fps[r].Pads()
                           if fps[r].GetLayer() != target_layer and d.GetAttribute() == p.PAD_ATTRIB_PTH])
    candidates = sorted(((tx+dx*.5,ty+dy*.5) for dx in range(-12,13) for dy in range(-12,13)),
                        key=lambda q:math.dist(q,(tx,ty)))
    found = None
    for x,y in candidates:
        f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y))); sh = court(f)
        if not outline.covers(sh) or same_side.intersects(sh): continue
        # Leave room under the modem's active inner LGA pads for ordinary
        # off-pad USB/SIM/boot fanout vias on a two-layer board.
        if side == 'B' and sh.intersects(unary_union([
            box(58.55,26.45,60.85,30.85),
            box(50.35,27.1,52.25,29.1),
            box(56.8,27.1,58.55,29.1),
        ])): continue
        pads = unary_union([copper(d,target_layer) for d in f.Pads()])
        if pads.intersects(through): continue
        found = (x,y); break
    if found is None: raise RuntimeError('No valid local placement for ' + ref)
    placed.add(ref); entries.append({'ref':ref,'target':[tx,ty],'actual_mm':found,'side':side,'angle':angle})
for q in data['parts']:
    f = fps[q['ref']]; q.update(x=xy(f.GetPosition())[0],y=xy(f.GetPosition())[1],angle=f.GetOrientationDegrees(),side='B' if f.GetLayer()==p.B_Cu else 'F')
data['two_layer_iterations'][-1]['packed_local_positions'] = entries
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity();p.SaveBoard(str(FILE),b)
(OUT/'exports/local-placement-packing.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
print('Placed',len(entries),'explicitly selected parts with unchanged full footprints. Native DRC required.')
