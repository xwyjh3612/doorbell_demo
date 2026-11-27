"""Accept a trial net only if it improves the native PCB without new errors."""
import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path

from comparison_route_geometry import b, FILE, p
from repair_comparison_groups import groups
from route_net_classes import PROTECTED

OUT = FILE.parent
REPO = Path(__file__).resolve().parents[2]
cli = REPO/'build/cad-tools/kicad/bin/kicad-cli.exe'
source = Path(os.environ['A18_ROUTE_TRANSFER']).resolve()
selected = os.environ['A18_TRANSFER_NETS'].split(',')
assert not PROTECTED.intersection(selected)
records = json.loads(source.read_text(encoding='utf-8'))['copper']
snapshot = OUT/'iterations'/('before-verified-net-merge-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE, snapshot/FILE.name)
probe = snapshot/FILE.name
for extension in ('.kicad_pro', '.kicad_dru'):
    shutil.copy2(FILE.with_suffix(extension), probe.with_suffix(extension))
for table in ('fp-lib-table', 'sym-lib-table'):
    table_path=OUT/table
    table_text=table_path.read_text(encoding='utf-8').replace('${KIPRJMOD}', OUT.as_posix())
    (snapshot/table).write_text(table_text, encoding='utf-8')
report_path = snapshot/'trial-drc.json'

def native_check():
    b.BuildConnectivity()
    assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(probe), b)
    subprocess.run([str(cli), 'pcb', 'drc', '--format', 'json', '--output', str(report_path), str(probe)], check=True, capture_output=True)
    return json.loads(report_path.read_text(encoding='utf-8'))

def hard(report):
    return [finding for finding in report['violations'] if finding['type'] not in {'track_dangling', 'via_dangling'}]

def clone(item):
    if item['via']:
        track=p.PCB_VIA(b)
        track.SetPosition(p.VECTOR2I(item['x'], item['y']))
        track.SetWidth(item['width']); track.SetDrill(item['drill'])
        track.SetLayerPair(p.F_Cu, p.B_Cu); track.SetViaType(p.VIATYPE_THROUGH)
    else:
        track=p.PCB_TRACK(b)
        track.SetStart(p.VECTOR2I(item['ax'], item['ay']))
        track.SetEnd(p.VECTOR2I(item['zx'], item['zy']))
        track.SetWidth(item['width']); track.SetLayer(item['layer'])
    track.SetNetCode(b.FindNet(item['net']).GetNetCode())
    b.Add(track)
    return track

baseline = native_check()
assert not hard(baseline), hard(baseline)
changes = []
removed_items = []
for net in selected:
    previous_groups = len(groups(net))
    if previous_groups < 2:
        continue
    previous_airwires = len(baseline['unconnected_items'])
    replacement = [item for item in records if item['net']==net]
    if not replacement:
        continue
    old = [track for track in b.GetTracks() if track.GetNetname()==net]
    for track in old:
        b.Remove(track)
    added = [clone(item) for item in replacement]
    candidate = native_check()
    current_groups = len(groups(net))
    current_airwires = len(candidate['unconnected_items'])
    accepted = not hard(candidate) and current_groups < previous_groups and current_airwires < previous_airwires
    change = {'net': net, 'accepted': accepted, 'pad_groups': [previous_groups, current_groups],
              'native_unconnected': [previous_airwires, current_airwires], 'hard_findings': hard(candidate)}
    changes.append(change)
    print(net, 'accepted' if accepted else 'rejected', change['pad_groups'], change['native_unconnected'], len(change['hard_findings']), flush=True)
    if accepted:
        removed_items.extend(old)
        baseline = candidate
        for track in added:
            track.SetLocked(True)
        p.SaveBoard(str(FILE), b)
    else:
        for track in added:
            b.Remove(track)
        removed_items.extend(added)
        for track in old:
            b.Add(track)
        b.BuildConnectivity()
        assert p.ZONE_FILLER(b).Fill(b.Zones())
out = OUT/'exports'/f'net-merge-{source.stem}.json'
out.write_text(json.dumps({'source': str(source), 'changes': changes}, indent=2), encoding='utf-8')
for track in removed_items:
    track.thisown = False
