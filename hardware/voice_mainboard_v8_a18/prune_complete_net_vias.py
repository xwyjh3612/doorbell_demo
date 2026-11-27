"""Batch prune native dangling vias on already connected nets.

The batch is accepted only if a fresh native check and geometric pad groups
prove connectivity was retained. Required pads and design rules are untouched.
"""
import datetime
import json
import shutil
import subprocess
from pathlib import Path

from comparison_route_geometry import b, FILE, p
from repair_comparison_groups import groups

repo = Path(__file__).resolve().parents[2]
cli = repo/'build/cad-tools/kicad/bin/kicad-cli.exe'
snapshot = FILE.parent/'iterations'/('batch-complete-vias-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE, snapshot/('before-'+FILE.name))
trial = snapshot/FILE.name
for suffix in ['.kicad_pro', '.kicad_dru']:
    shutil.copy2(FILE.with_suffix(suffix), trial.with_suffix(suffix))
for name in ['fp-lib-table', 'sym-lib-table']:
    source = FILE.parent/name
    if source.exists():
        (snapshot/name).write_text(source.read_text(encoding='utf-8').replace('${KIPRJMOD}', FILE.parent.as_posix()), encoding='utf-8')

def check():
    b.BuildConnectivity()
    assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(trial), b)
    subprocess.run([str(cli), 'pcb', 'drc', '--format', 'json', '--output', str(snapshot/'drc.json'), str(trial)], check=True, capture_output=True)
    return json.loads((snapshot/'drc.json').read_text(encoding='utf-8'))

def hard(report):
    return sum(q['type'] not in ['track_dangling', 'via_dangling'] for q in report['violations'])

before = check()
assert hard(before) == 0
objects = {t.m_Uuid.AsString(): t for t in b.GetTracks()}
counts = {}
removed = []
for finding in before['violations']:
    if finding['type'] != 'via_dangling':
        continue
    t = objects.get(finding['items'][0]['uuid'])
    if t is None:
        continue
    net = t.GetNetname()
    counts.setdefault(net, len(groups(net)))
    if counts[net] > 1:
        continue
    b.Remove(t)
    removed.append(t)
after = check()
accepted = (hard(after) == 0 and len(after['unconnected_items']) <= len(before['unconnected_items'])
            and all(len(groups(net)) <= count for net, count in counts.items()))
if not accepted:
    for t in removed:
        b.Add(t)
    b.BuildConnectivity()
    assert p.ZONE_FILLER(b).Fill(b.Zones())
else:
    p.SaveBoard(str(FILE), b)
report = {'accepted': accepted,
          'removed_vias': [{'uuid': t.m_Uuid.AsString(), 'net': t.GetNetname()} for t in removed] if accepted else [],
          'before': {k: len(before[k]) for k in ['violations', 'unconnected_items']},
          'candidate_after': {k: len(after[k]) for k in ['violations', 'unconnected_items']},
          'pad_groups_before': counts, 'pad_or_rule_changes': False}
(FILE.parent/'exports/batch-complete-via-pruning.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
if accepted:
    for t in removed:
        t.thisown = False
print('Batch complete-net via pruning:', 'accepted' if accepted else 'rolled back',
      '; removed:', len(report['removed_vias']), '; native:', report['candidate_after'])
