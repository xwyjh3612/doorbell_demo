"""Start an isolated two-layer revision, preserving both reviewed comparisons.

Only placement is carried from the four-layer comparison. Its inner-layer
copper is discarded, never projected onto another layer. Pad nets are fixed.
"""
from pathlib import Path
import datetime, hashlib, json, shutil
import pcbnew as p

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'comparison_clean_4layer'
OUT = ROOT / 'two_layer_work'
NAME = 'voice_mainboard_a18_2layer'
if OUT.exists():
    raise RuntimeError('Working revision already exists; do not overwrite it.')
snapshot = ROOT / 'history' / ('two-layer-before-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
shutil.copytree(ROOT / 'comparison_clean_2layer', snapshot)
OUT.mkdir()
(OUT / 'exports').mkdir()
for ext in ['kicad_sch', 'kicad_pro', 'kicad_dru']:
    shutil.copy2(SOURCE / ('voice_mainboard_a18_clean_4layer.' + ext), OUT / (NAME + '.' + ext))
for table in ['fp-lib-table', 'sym-lib-table']:
    shutil.copy2(SOURCE / table, OUT / table)
b = p.LoadBoard(str(SOURCE / 'voice_mainboard_a18_clean_4layer.kicad_pcb'))
padnets = lambda: sorted((f.GetReference(), d.GetNumber(), d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
before = padnets()
held = []
for item in list(b.GetTracks()):
    held.append(item); b.Remove(item)
for zone in list(b.Zones()):
    if not zone.GetIsRuleArea():
        held.append(zone); b.Remove(zone)
b.SetCopperLayerCount(2)
fps = {f.GetReference(): f for f in b.GetFootprints()}
data = json.loads((SOURCE / 'design.json').read_text(encoding='utf-8'))
parts = {q['ref']: q for q in data['parts']}
old = {}
# Move the modem supply off the ESP-side signal corridor, keeping its
# output beside modem supply pads. The converter loop still needs review.
moves = {
    'U2': (55.5, 8.5, 180, 'B'), 'L1': (54.5, 13.8, 270, 'B'),
    'C4': (60, 8, 0, 'B'), 'C6': (60.5, 12.5, 0, 'B'),
    'C7': (60.5, 16.3, 0, 'B'), 'R2': (60, 5, 90, 'B'),
    'R3': (63, 5, 90, 'B'), 'C37': (64, 9.5, 0, 'B'),
    # Reset transistor/filter close to the modem, rather than a long
    # RESET_N line crossing the audio/power region.
    'Q2': (45, 35.5, 180, 'B'), 'C19': (48, 35.5, 90, 'B'),
    'R8': (42, 35.5, 90, 'B'),
}
for ref, (x, y, angle, side) in moves.items():
    f = fps[ref]
    old[ref] = [p.ToMM(f.GetPosition().x), p.ToMM(f.GetPosition().y), f.GetOrientationDegrees(), 'B' if f.GetLayer() == p.B_Cu else 'F']
    f.SetPosition(p.VECTOR2I(p.FromMM(x), p.FromMM(y)))
    layer = p.B_Cu if side == 'B' else p.F_Cu
    if f.GetLayer() != layer:
        f.Flip(f.GetPosition(), False)
    f.SetOrientationDegrees(angle)
for ref, f in fps.items():
    if ref in parts:
        parts[ref].update(x=p.ToMM(f.GetPosition().x), y=p.ToMM(f.GetPosition().y),
                          angle=f.GetOrientationDegrees(), side='B' if f.GetLayer() == p.B_Cu else 'F')
assert before == padnets(), 'Placement must not change pad nets'
data.update(layers=2, revision='A18 TWO-LAYER WORK REVISION', manufacturing_ready=False,
            status='PLACEMENT AND ROUTING REVIEW REQUIRED',
            selected_production_layer_count=2)
data['two_layer_relayout'] = {'source': str(SOURCE.relative_to(ROOT)),
    'discarded_all_source_tracks': True, 'previous_positions': old,
    'moves': moves, 'historical_two_layer_snapshot': str(snapshot.relative_to(ROOT))}
(OUT / 'design.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
b.BuildConnectivity()
p.SaveBoard(str(OUT / (NAME + '.kicad_pcb')), b)
(OUT / 'exports' / 'placement-origin.json').write_text(json.dumps({
    'source_sha256': hashlib.sha256((SOURCE / 'voice_mainboard_a18_clean_4layer.kicad_pcb').read_bytes()).hexdigest(),
    'pad_net_contract_count': sum(bool(q[2]) and not q[2].startswith('unconnected-') for q in before),
    'moved_parts': moves, 'snapshot': str(snapshot.relative_to(ROOT)),
}, ensure_ascii=False, indent=2), encoding='utf-8')
for item in held:
    item.thisown = False
print('Created independent two-layer work; source copper discarded and all pad nets retained.')
