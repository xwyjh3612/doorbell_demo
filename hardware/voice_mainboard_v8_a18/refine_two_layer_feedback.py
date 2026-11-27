"""Freeze nearby feedback placement and retire only obsolete copper.

Preserve the component/pad/net contract. Snapshot before modifying the board;
all copper changes are recorded and must be reconnected and checked natively.
"""
from pathlib import Path
import datetime, json, shutil
import pcbnew as p

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'two_layer_work'
FILE = OUT / 'voice_mainboard_a18_2layer.kicad_pcb'
snapshot = OUT / 'iterations' / ('before-feedback-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
for name in [FILE.name, 'design.json']:
    shutil.copy2(OUT / name, snapshot / name)
b = p.LoadBoard(str(FILE))
fps = {f.GetReference(): f for f in b.GetFootprints()}
contract = lambda: sorted((f.GetReference(), d.GetNumber(), d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
before = contract()
moves = {
    'R2': (54.25, 5.1, 270, 'B'), 'R3': (58.25, 2.0, 0, 'B'),
    'C37': (56.25, 5.1, 270, 'B'), 'C4': (59.5, 8, 0, 'B'),
    'C5': (59.25, 5.5, 0, 'B'), 'R59': (21.5, 24, 180, 'F'),
    'R60': (18, 24, 0, 'F'), 'C63': (21.5, 24, 180, 'B'),
    'C73': (70, 40.9, 0, 'B'),
}
points = {(d.GetPosition().x, d.GetPosition().y) for ref in moves for d in fps[ref].Pads()}
removed, held = [], []
for t in list(b.GetTracks()):
    incident = any((q.x, q.y) in points for q in [t.GetStart(), t.GetEnd()])
    if t.GetNetname() in ['BUCK_FB', 'ESP_FB'] or incident:
        removed.append({'uuid': t.m_Uuid.AsString(), 'net': t.GetNetname(), 'reason': 'feedback-relocation'})
        held.append(t)
        b.Remove(t)
for ref, (x, y, angle, side) in moves.items():
    f = fps[ref]
    layer = p.B_Cu if side == 'B' else p.F_Cu
    if f.GetLayer() != layer:
        f.Flip(f.GetPosition(), False)
    f.SetPosition(p.VECTOR2I(p.FromMM(x), p.FromMM(y)))
    f.SetOrientationDegrees(angle)
assert contract() == before
data = json.loads((OUT / 'design.json').read_text(encoding='utf-8'))
for q in data['parts']:
    f = fps[q['ref']]
    q.update(x=p.ToMM(f.GetPosition().x), y=p.ToMM(f.GetPosition().y),
             angle=f.GetOrientationDegrees(), side='B' if f.GetLayer() == p.B_Cu else 'F')
data.setdefault('two_layer_iterations', []).append({'snapshot': str(snapshot.relative_to(OUT)),
    'reason': 'Shorter buck feedback paths and boost output decoupling near power mux', 'moves': moves})
(OUT / 'design.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE), b)
(OUT / 'exports/feedback-refinement.json').write_text(json.dumps({'moves': moves, 'removed_routes': removed}, indent=2), encoding='utf-8')
# Independent placement-only DRC distinguishes pad/footprint issues from old routing.
for t in list(b.GetTracks()):
    held.append(t)
    b.Remove(t)
for z in list(b.Zones()):
    if not z.GetIsRuleArea():
        held.append(z)
        b.Remove(z)
p.SaveBoard(str(OUT / 'exports/placement-only.kicad_pcb'), b)
for t in held:
    t.thisown = False
print('Feedback placement frozen; pad/net contract unchanged. Placement-only copy exported.')
