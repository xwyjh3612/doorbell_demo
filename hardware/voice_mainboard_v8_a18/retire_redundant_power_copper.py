"""Retire named redundant supply segments without worsening reviewed paths."""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

from comparison_route_geometry import b, FILE, p
from repair_comparison_groups import groups
from audit_copper_paths import trace_path

PAIRS = {
    'BAT_BOOST_5V': [(('U15',7),('U18',6))],
    'VIN_PROTECTED': [(('Q6',2),('U18',3))],
    'SYS_5V': [(('U18',2),('U2',4)),(('U18',2),('U14',7)),(('U18',2),('U13',4))],
}
repo=Path(__file__).resolve().parents[2]
cli=repo/'build/cad-tools/kicad/bin/kicad-cli.exe'
out=FILE.parent/'iterations'/('redundant-supply-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True);shutil.copy2(FILE,out/('before-'+FILE.name))
trial=out/FILE.name
for suffix in ['.kicad_pro','.kicad_dru']:
    shutil.copy2(FILE.with_suffix(suffix),trial.with_suffix(suffix))
for name in ['fp-lib-table','sym-lib-table']:
    source=FILE.parent/name
    if source.exists():
        (out/name).write_text(source.read_text(encoding='utf-8').replace('${KIPRJMOD}',FILE.parent.as_posix()),encoding='utf-8')
def check():
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(trial),b)
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(out/'drc.json'),str(trial)],check=True,capture_output=True)
    return json.loads((out/'drc.json').read_text(encoding='utf-8'))
def hard(q):return [e for e in q['violations'] if e['type'] not in ['track_dangling','via_dangling']]
report=check();assert not hard(report)
log=[];held=[]
for uid in os.environ['A18_REDUNDANT_POWER_UUIDS'].split(','):
    t=next((t for t in b.GetTracks() if t.m_Uuid.AsString()==uid),None)
    if t is None:continue
    net=t.GetNetname();assert net in PAIRS and not isinstance(t,p.PCB_VIA)
    before_groups=len(groups(net));before=report
    paths_before=[trace_path(a,z) for a,z in PAIRS[net]]
    b.Remove(t);b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
    paths_after=[trace_path(a,z) for a,z in PAIRS[net]]
    okay=(len(groups(net))<=before_groups and all(q['trace_graph_connected'] and r['trace_graph_connected']
          and q['estimated_R_20C_ohm']<=r['estimated_R_20C_ohm']+.000001 for q,r in zip(paths_after,paths_before)))
    if okay:
        candidate=check();okay=not hard(candidate) and len(candidate['unconnected_items'])<=len(before['unconnected_items'])
    if okay:
        held.append(t);report=candidate;p.SaveBoard(str(FILE),b)
    else:
        b.Add(t);b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
    log.append({'uuid':uid,'net':net,'accepted':okay,'paths_before':paths_before,'paths_after':paths_after})
    print('Redundant supply segment',net,uid,'retired' if okay else 'retained',flush=True)
(FILE.parent/'exports/redundant-supply-retirement.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
for t in held:t.thisown=False
