"""Remove copper explicitly identified by a fresh native DRC report.

No pads, footprints, rules or exclusions may be changed. Retired nets remain
mandatory connections. A new DRC is required after every pass.
"""
from pathlib import Path
import datetime, json, os, shutil, sys
import pcbnew as p

FILE = Path(os.environ['A18_REPAIR_BOARD']).resolve()
OUT = FILE.parent / 'exports'
report_path = Path(sys.argv[1]).resolve()
report = json.loads(report_path.read_text(encoding='utf-8'))
assert report['source'] == FILE.name
b = p.LoadBoard(str(FILE))
tracks = {t.m_Uuid.AsString(): t for t in b.GetTracks()}
ids, unresolved = set(), []
allowed = {'shorting_items', 'tracks_crossing', 'clearance', 'solder_mask_bridge', 'via_dangling', 'track_dangling'}
for finding in report['violations']:
    # Dangling ends may belong to traces that also serve real intermediate
    # junctions. Use prune_dangling_copper_verified.py for these findings.
    if finding['type'] in {'via_dangling','track_dangling'} and os.environ.get('A18_UNVERIFIED_DANGLING_RETIREMENT')!='1':
        continue
    if finding['type'] not in allowed:
        unresolved.append(finding)
        continue
    candidates = [q['uuid'] for q in finding['items'] if q['uuid'] in tracks]
    selected_nets=set(filter(None,os.environ.get('A18_RETIRE_ONLY_NETS','').split(',')))
    if selected_nets:
        candidates=[uid for uid in candidates if tracks[uid].GetNetname() in selected_nets]
        if not candidates:continue
    if os.environ.get('A18_RETAIN_LOCKED_COPPER')=='1':
        candidates=[uid for uid in candidates if not tracks[uid].IsLocked()]
    if not candidates:
        unresolved.append(finding)
        continue
    ids.update(candidates)
snapshot = FILE.parent / 'iterations' / ('before-copper-cleanup-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE, snapshot / FILE.name)
changes, held = [], []
for uid in ids:
    t = tracks[uid]
    changes.append({'uuid': uid, 'net': t.GetNetname(), 'was_locked': t.IsLocked()})
    held.append(t)
    b.Remove(t)
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE), b)
log = OUT / 'copper-retirement-history.json'
history = json.loads(log.read_text(encoding='utf-8')) if log.exists() else []
history.append({'native_report': str(report_path), 'snapshot': str(snapshot),
                'removed': changes, 'unresolved_non_copper_findings': unresolved})
log.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
for t in held:
    t.thisown = False
print(json.dumps({'removed_tracks_vias': len(changes), 'non_copper_findings': len(unresolved)}))
