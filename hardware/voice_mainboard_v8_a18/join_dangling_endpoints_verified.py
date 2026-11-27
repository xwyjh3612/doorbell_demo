"""Join short dangling ends to existing same-net centre lines/pad centres.

Do not rely on geometric edge-touching alone. Every candidate is independently
checked by KiCad and must lower native dangling findings without adding any
hard error, airwire or disconnected physical pad group. No rules are changed.
"""
import datetime
import json
import math
from pathlib import Path
import shutil
import subprocess

from comparison_route_geometry import b, FILE, p, pos, polys
from repair_comparison_groups import groups
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points

cli = Path(__file__).resolve().parents[2] / 'build/cad-tools/kicad/bin/kicad-cli.exe'
out = FILE.parent / 'iterations' / ('joined-endpoints-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)
shutil.copy2(FILE, out / ('before-' + FILE.name))
probe = out / FILE.name
for suffix in ('.kicad_pro', '.kicad_dru'):
    shutil.copy2(FILE.with_suffix(suffix), probe.with_suffix(suffix))
for name in ('fp-lib-table', 'sym-lib-table'):
    text = (FILE.parent / name).read_text(encoding='utf-8').replace('${KIPRJMOD}', FILE.parent.as_posix())
    (out / name).write_text(text, encoding='utf-8')

def hard(report):
    return [v for v in report['violations'] if v['type'] not in ('track_dangling', 'via_dangling')]

def check():
    b.BuildConnectivity()
    assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(probe), b)
    subprocess.run([str(cli), 'pcb', 'drc', '--format', 'json', '--output', str(out/'drc.json'), str(probe)],
                   check=True, capture_output=True)
    return json.loads((out/'drc.json').read_text(encoding='utf-8'))

report = check()
assert not hard(report)
changes = []
rejected = set()
for iteration in range(100):
    tracks = {t.m_Uuid.AsString(): t for t in b.GetTracks()}
    candidates = []
    for finding in report['violations']:
        if finding['type'] != 'track_dangling':
            continue
        t = tracks.get(finding['items'][0]['uuid'])
        if t is None or isinstance(t, p.PCB_VIA):
            continue
        net = t.GetNetname()
        for endpoint in ('start', 'end'):
            v = t.GetStart() if endpoint == 'start' else t.GetEnd()
            xy = (p.ToMM(v.x), p.ToMM(v.y))
            goals = []
            for f in b.GetFootprints():
                for pad in f.Pads():
                    if pad.GetNetname() == net and pad.IsOnLayer(t.GetLayer()):
                        goals.append(pos(pad))
            for other in tracks.values():
                if other == t or other.GetNetname() != net or not other.IsOnLayer(t.GetLayer()):
                    continue
                if isinstance(other, p.PCB_VIA):
                    goals.append(pos(other))
                else:
                    a, z = other.GetStart(), other.GetEnd()
                    line = LineString([(p.ToMM(a.x), p.ToMM(a.y)), (p.ToMM(z.x), p.ToMM(z.y))])
                    q = nearest_points(Point(xy), line)[1]
                    goals.append((q.x, q.y))
            options = sorted({q for q in goals if .0001 < math.dist(q, xy) <= 1.5}, key=lambda q: math.dist(q, xy))
            for goal in options[:4]:
                key = (t.m_Uuid.AsString(), endpoint, goal)
                if key not in rejected:
                    candidates.append((math.dist(xy, goal), key, t, endpoint, xy, goal))
    accepted = False
    for _, key, t, endpoint, xy, goal in sorted(candidates, key=lambda q:q[0]):
        before_groups = len(groups(t.GetNetname()))
        original = p.VECTOR2I(t.GetStart() if endpoint == 'start' else t.GetEnd())
        wanted = p.VECTOR2I(p.FromMM(goal[0]), p.FromMM(goal[1]))
        if endpoint == 'start': t.SetStart(wanted)
        else: t.SetEnd(wanted)
        candidate = check()
        if (not hard(candidate) and len(candidate['violations']) < len(report['violations'])
                and len(candidate['unconnected_items']) <= len(report['unconnected_items'])
                and len(groups(t.GetNetname())) <= before_groups):
            change = {'uuid': t.m_Uuid.AsString(), 'net': t.GetNetname(), 'end': endpoint,
                      'from': xy, 'to': goal, 'native_findings': [len(report['violations']),len(candidate['violations'])],
                      'native_unconnected': [len(report['unconnected_items']),len(candidate['unconnected_items'])]}
            changes.append(change)
            report = candidate
            p.SaveBoard(str(FILE), b)
            print('Joined',t.GetNetname(),endpoint,'native',len(report['violations']),len(report['unconnected_items']),flush=True)
            accepted = True
            break
        if endpoint == 'start': t.SetStart(original)
        else: t.SetEnd(original)
        rejected.add(key)
    if not accepted:
        break
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE), b)
(FILE.parent/'exports/joined-endpoints-review.json').write_text(json.dumps({'changes':changes,
    'rejected_candidates':len(rejected),'native_findings':len(report['violations']),
    'native_unconnected':len(report['unconnected_items'])},indent=2),encoding='utf-8')
print('Endpoint review finished:',len(changes),'joins; native',len(report['violations']),len(report['unconnected_items']),flush=True)
