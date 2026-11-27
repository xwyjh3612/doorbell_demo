"""Repartition the two-layer buses after a measured first routing attempt.

Snapshot the previous result, discard all old copper, then move translators
beside the modem and the amplifier beside the ESP audio pins. Same BOM/nets.
"""
from pathlib import Path
import datetime, json, shutil
import pcbnew as p
ROOT = Path(__file__).resolve().parent / 'two_layer_work'
FILE = ROOT / 'voice_mainboard_a18_2layer.kicad_pcb'
snap = ROOT / 'iterations' / ('before-bus-repartition-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snap.mkdir(parents=True)
for name in [FILE.name, 'design.json', 'signals.dsn', 'signals.ses']:
    shutil.copy2(ROOT / name, snap / name)
shutil.copytree(ROOT / 'exports', snap / 'exports')
b = p.LoadBoard(str(FILE)); held = []
contract = lambda: sorted((f.GetReference(), d.GetNumber(), d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
before = contract()
for item in list(b.GetTracks()):
    held.append(item); b.Remove(item)
for zone in list(b.Zones()):
    if not zone.GetIsRuleArea():
        held.append(zone); b.Remove(zone)
fps = {f.GetReference(): f for f in b.GetFootprints()}
data = json.loads((ROOT / 'design.json').read_text(encoding='utf-8'))
parts = {q['ref']: q for q in data['parts']}
moves = {
    'U3': (52.5, 36.5, 0, 'B'), 'U4': (56, 36.5, 0, 'B'),
    'U5': (60, 32.5, 90, 'B'),
    'C13': (51, 39, 90, 'B'), 'C14': (54, 39, 90, 'B'),
    'C15': (56, 39, 90, 'B'), 'C16': (58, 39, 90, 'B'),
    'C17': (57, 32.5, 0, 'B'), 'C18': (60, 29, 0, 'B'),
    'Q2': (48.5, 35.5, 180, 'B'), 'C19': (46, 33.5, 90, 'B'),
    'R8': (46, 36.5, 90, 'B'),
    'U14': (35, 48, 0, 'F'),
    'C61': (31.5, 51.5, 90, 'F'), 'C62': (35, 51.5, 0, 'F'),
    'R75': (39.5, 48.5, 0, 'F'), 'R76': (39, 52, 0, 'F'),
    'R26': (65.5, 31.5, 0, 'F'), 'R27': (65.5, 33.5, 0, 'F'),
    'R28': (47.5, 45, 0, 'F'), 'R29': (50.5, 46, 0, 'F'),
    'R30': (66.5, 29, 0, 'F'),
}
previous = {}
for ref, (x, y, angle, side) in moves.items():
    f = fps[ref]
    previous[ref] = [p.ToMM(f.GetPosition().x), p.ToMM(f.GetPosition().y), f.GetOrientationDegrees(), 'B' if f.GetLayer() == p.B_Cu else 'F']
    f.SetPosition(p.VECTOR2I(p.FromMM(x), p.FromMM(y)))
    if f.GetLayer() != (p.B_Cu if side == 'B' else p.F_Cu):
        f.Flip(f.GetPosition(), False)
    f.SetOrientationDegrees(angle)
for ref, f in fps.items():
    parts[ref].update(x=p.ToMM(f.GetPosition().x), y=p.ToMM(f.GetPosition().y), angle=f.GetOrientationDegrees(), side='B' if f.GetLayer() == p.B_Cu else 'F')
assert contract() == before
data.setdefault('two_layer_iterations', []).append({'snapshot': str(snap.relative_to(ROOT)),
    'reason': 'First routed revision: native copper clearance passes, but blocked bus exits remain. Move translators beside modem and amplifier beside ESP audio pins.',
    'moves': moves, 'previous_positions': previous})
data.update(status='BUS REPARTITION PLACEMENT CHECK REQUIRED', manufacturing_ready=False)
(ROOT / 'design.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
b.BuildConnectivity(); p.SaveBoard(str(FILE), b)
for item in held:
    item.thisown = False
print('Bus repartition preserved the complete pad-net contract; native placement DRC required.')
