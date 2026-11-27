"""Re-plan obsolete ground stitches in an explicitly named signal corridor.

The ground plane is refilled and every physical pad group and native finding
is checked before retaining the change. No pad, part, net or rule is changed.
This addresses ground tracks acting as walls in the two-layer search, rather
than repeatedly attempting a route through the same fixed copper pocket.
"""
import datetime
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from comparison_route_geometry import b, FILE, p, pos, route, layers
from repair_comparison_groups import groups
from shapely.geometry import LineString, Point

repo = Path(__file__).resolve().parents[2]
cli = repo / 'build/cad-tools/kicad/bin/kicad-cli.exe'
out = FILE.parent / 'iterations' / ('ground-corridors-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)
trial = out / FILE.name
for suffix in ('.kicad_pro', '.kicad_dru'):
    shutil.copy2(FILE.with_suffix(suffix), trial.with_suffix(suffix))
shutil.copy2(FILE, out / ('before-' + FILE.name))
for name in ('fp-lib-table', 'sym-lib-table'):
    source = FILE.parent / name
    if source.exists():
        (out / name).write_text(source.read_text(encoding='utf-8').replace('${KIPRJMOD}', FILE.parent.as_posix()), encoding='utf-8')
netnames = sorted({d.GetNetname() for f in b.GetFootprints() for d in f.Pads()
                   if d.GetNetname() and not d.GetNetname().startswith('unconnected-')})

def refill():
    b.BuildConnectivity()
    assert p.ZONE_FILLER(b).Fill(b.Zones())

def check():
    refill()
    p.SaveBoard(str(trial), b)
    subprocess.run([str(cli), 'pcb', 'drc', '--format', 'json', '--output', str(out / 'drc.json'), str(trial)], check=True, capture_output=True)
    return json.loads((out / 'drc.json').read_text(encoding='utf-8'))

def hard(report):
    return [q for q in report['violations'] if q['type'] not in ('track_dangling', 'via_dangling')]

def shape(t):
    if isinstance(t, p.PCB_VIA):
        return Point(pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu)) / 2)
    return LineString([(p.ToMM(q.x), p.ToMM(q.y)) for q in (t.GetStart(), t.GetEnd())]).buffer(p.ToMM(t.GetWidth()) / 2)

report = check()
assert not hard(report)
held = []
log = []
for net in os.environ['A18_ONLY_NETS'].split(','):
    baseline_groups = {n: len(groups(n)) for n in netnames}
    gs = groups(net, add_track_anchors=True)
    if len(gs) < 2:
        continue
    candidates = sorted(((math.dist(pos(a), pos(z)), i, j, a, z)
                         for i, g in enumerate(gs) for j, h in enumerate(gs) if j > i
                         for a in g for z in h), key=lambda q: q[0])
    diverse = []
    for pair in candidates:
        if any(math.dist(pos(pair[3]), pos(q[3])) < 1.2 and math.dist(pos(pair[4]), pos(q[4])) < 1.2 for q in diverse):
            continue
        diverse.append(pair)
        if len(diverse) >= 3:
            break
    accepted = False
    for _, _, _, a, z in diverse:
        for margin in (0.65, 1.5):
            before_tracks = {t.m_Uuid.AsString(): t for t in b.GetTracks()}
            corridor = LineString([pos(a), pos(z)]).buffer(margin)
            removed = [t for t in b.GetTracks() if t.GetNetname() == 'GND' and shape(t).intersects(corridor)]
            if not removed:
                continue
            for t in removed:
                b.Remove(t)
            refill()
            entry = {'net': net, 'from': pos(a), 'to': pos(z), 'margin': margin,
                     'retired_ground': [t.m_Uuid.AsString() for t in removed]}
            try:
                change = route(net, pos(a), pos(z), {i for i, l in enumerate(layers) if a.IsOnLayer(l)},
                               {i for i, l in enumerate(layers) if z.IsOnLayer(l)}, width=.16, step=.05)
                candidate = check()
                after_groups = {n: len(groups(n)) for n in netnames}
                entry.update(change=change, hard=hard(candidate), native_unconnected=len(candidate['unconnected_items']),
                             worsened_groups={n: [baseline_groups[n], k] for n, k in after_groups.items() if k > baseline_groups[n]})
                accepted = (not hard(candidate) and not entry['worsened_groups']
                            and len(candidate['unconnected_items']) < len(report['unconnected_items'])
                            and len(candidate['violations']) <= len(report['violations']))
                if accepted:
                    held.extend(removed)
                    report = candidate
                    p.SaveBoard(str(FILE), b)
            except RuntimeError as error:
                entry['error'] = str(error)
            entry['accepted'] = accepted
            log.append(entry)
            if not accepted:
                for t in list(b.GetTracks()):
                    if t.m_Uuid.AsString() not in before_tracks:
                        b.Remove(t)
                        held.append(t)
                for t in removed:
                    b.Add(t)
                refill()
            print(net, 'accepted' if accepted else 'rejected', 'margin', margin,
                  'ground pieces', len(removed), 'native', len(report['unconnected_items']), flush=True)
            (FILE.parent / 'exports/ground-corridor-review.json').write_text(json.dumps(log, indent=2), encoding='utf-8')
            if accepted:
                break
        if accepted:
            break
refill()
p.SaveBoard(str(FILE), b)
for t in held:
    t.thisown = False
