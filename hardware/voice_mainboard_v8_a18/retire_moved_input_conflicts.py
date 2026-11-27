"""Retire copper crossing the newly placed input/charge-control pads.

No pad or rule is modified. Modem/ESP main supplies are checked explicitly;
only colliding branch copper is retired, then all branches must be rebuilt.
"""
import datetime
import json
import shutil
import subprocess
from pathlib import Path

from comparison_route_geometry import b, FILE, p
from audit_copper_paths import trace_path
from route_net_classes import PROTECTED

out=FILE.parent/'exports'
cli=Path(__file__).resolve().parents[2]/'build/cad-tools/kicad/bin/kicad-cli.exe'
snapshot=FILE.parent/'iterations'/('before-input-conflict-retirement-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True);shutil.copy2(FILE,snapshot/FILE.name)
pairs=[(('U15',7),('U18',6)),(('L5',2),('U7',2))]
before=[trace_path(a,z) for a,z in pairs]
assert all(q['trace_graph_connected'] for q in before),'Explicit main supply paths must exist before branch retirement'
changed={'J1','F1','C73','Q7','R68','R69'}
def check():
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(out/'input-conflict-drc.json'),str(FILE)],check=True,capture_output=True)
    return json.loads((out/'input-conflict-drc.json').read_text(encoding='utf-8'))
records=[];held=[]
for iteration in range(3):
    report=check()
    pads={d.m_Uuid.AsString():f.GetReference() for f in b.GetFootprints() for d in f.Pads()}
    tracks={t.m_Uuid.AsString():t for t in b.GetTracks()}
    selected={}
    for q in report['violations']:
        if q['type'] in ['track_dangling','via_dangling']:continue
        if not any(pads.get(item['uuid']) in changed for item in q['items']):continue
        for item in q['items']:
            t=tracks.get(item['uuid'])
            if t is None:continue
            assert t.GetNetname() not in PROTECTED or t.GetNetname() in {'GND','ESP_3V3','BAT_BOOST_5V'},t.GetNetname()
            selected[item['uuid']]=t
    if not selected:break
    for t in selected.values():
        records.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'via':isinstance(t,p.PCB_VIA)})
        b.Remove(t);held.append(t)
    after=[trace_path(a,z) for a,z in pairs]
    for previous,current in zip(before,after):
        assert not previous['trace_graph_connected'] or (current['trace_graph_connected']
            and current['estimated_R_20C_ohm']<=previous['estimated_R_20C_ohm']+.00001),'Main supply path changed'
report=check()
(out/'input-conflict-retirement.json').write_text(json.dumps({'snapshot':str(snapshot),'retired_copper':records,
    'main_paths_before':before,'main_paths_after':[trace_path(a,z) for a,z in pairs],
    'remaining_native_counts':{key:len(report[key]) for key in ['violations','unconnected_items']},
    'status':'Input branches and charge-control routing require completion'},indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Retired conflicting input branch copper:',len(records),'native',len(report['violations']),len(report['unconnected_items']),flush=True)
