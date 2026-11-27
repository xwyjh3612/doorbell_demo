"""Give isolated IC pad groups an ordinary off-pad escape before routing buses.

Each child process loads the latest saved PCB and validates its own candidate
with native rules. This avoids routing an entire bus through a dense pad row.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from comparison_route_geometry import b, FILE, p
from repair_comparison_groups import groups
from route_net_classes import PROTECTED

selected=set(filter(None,os.environ['A18_FANOUT_NETS'].split(',')))
assert not selected.intersection(PROTECTED)
refs={'U7','U1','U3','U4','U5','U14','U16','U18'}
plans=[]
for net in sorted(selected):
    gs=groups(net)
    if len(gs)<2:continue
    for group in gs:
        if any(isinstance(q,p.PCB_VIA) for q in group):continue
        pads=[q for q in group if isinstance(q,p.PAD) and q.GetParentFootprint().GetReference() in refs]
        if not pads:continue
        d=pads[0]
        plans.append({'net':net,'pad':d.GetParentFootprint().GetReference()+'.'+d.GetNumber()})
(FILE.parent/'exports/ic-fanout-plans.json').write_text(json.dumps(plans,indent=2),encoding='utf-8')
script=Path(__file__).with_name('escape_pad_with_route.py')
for plan in plans:
    env=dict(os.environ,A18_ESCAPE_PAD=plan['pad'],A18_NECK_WIDTH='.16',A18_NECK_VIA_DIAMETER='.45',
             A18_NECK_VIA_DRILL='.2',A18_NECK_SEARCH_RADIUS='3.2',A18_NECK_TRIAL_LIMIT='3')
    env.pop('A18_NECK_VIA_POINTS',None)
    result=subprocess.run([sys.executable,str(script)],env=env,capture_output=True,text=True)
    report=FILE.parent/'exports'/('bent-neck-'+plan['pad'].replace('.','-')+'.json')
    if result.returncode:
        print(plan,'failed',result.stderr[-400:],flush=True)
        raise RuntimeError('IC escape process failed')
    saved=json.loads(report.read_text(encoding='utf-8'))
    print(plan,'native-accepted',saved['success'],flush=True)
