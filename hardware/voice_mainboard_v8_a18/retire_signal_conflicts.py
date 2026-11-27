"""Retire ordinary signal copper named in a native DRC conflict report.

Required pads, fixed supply/ground copper and design rules cannot be removed.
Each removal is recorded; remaining nets must be routed and checked again.
"""
import datetime
import json
from pathlib import Path
import shutil
import sys

from comparison_route_geometry import b, FILE, p
from route_net_classes import PROTECTED

report_path = Path(sys.argv[1]).resolve()
drc = json.loads(report_path.read_text(encoding='utf-8'))
tracks = {t.m_Uuid.AsString(): t for t in b.GetTracks()}
to_remove = {}
unresolved = []
for finding in drc['violations']:
    if finding['type'] in ('via_dangling', 'track_dangling', 'isolated_copper'):
        continue
    removable = []
    for item in finding['items']:
        t = tracks.get(item['uuid'])
        if t is not None and t.GetNetname() not in PROTECTED and not t.IsLocked():
            removable.append(t)
    if not removable:
        unresolved.append(finding)
    for t in removable:
        to_remove[t.m_Uuid.AsString()] = t
snapshot = FILE.parent/'iterations'/('before-signal-conflict-retirement-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE, snapshot/FILE.name)
removed = []
for uid, t in to_remove.items():
    removed.append({'uuid': uid, 'net': t.GetNetname(), 'via': isinstance(t, p.PCB_VIA)})
    b.Remove(t)
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE), b)
for t in to_remove.values():
    t.thisown = False
out = {'input_DRC': str(report_path), 'removed_ordinary_items': removed,
       'protected_or_pad_conflicts_remaining': unresolved,
       'pad_or_rule_changes': False, 'native_DRC_and_reconnection_required': True}
(FILE.parent/'exports/signal-conflict-retirement.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print('Retired ordinary items:', len(removed), '; protected/pad conflicts:', len(unresolved))
