"""Evaluate the local decoupling link that cuts the modem's ground island.

An isolated trial only. Preserve physical supply connectivity; the candidate
must pass native checks before a separate acceptance step.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
from comparison_route_geometry import b,FILE,p,pos,route,layers
from repair_comparison_groups import groups
from route_net_classes import PROTECTED

root=Path(__file__).resolve().parents[2]
out=FILE.parent/'exports'
snapshot=FILE.parent/'iterations'/('ground-decoupling-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True);shutil.copy2(FILE,snapshot/FILE.name)
before={net:len(groups(net))for net in PROTECTED if b.FindNet(net)}
ids={'4c3ae65b-b59f-4a73-8be8-969011664811','8fc1881d-deb2-4eec-bf0c-1ce6730978f1','9084a159-a5d0-4847-8131-2e649e9f7030','94eda931-1159-4a7c-9d2f-e983c47b6121'}
removed=[]
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString()in ids:
        assert t.GetNetname()=='MODEM_3V8'and t.GetLayer()==p.F_Cu
        removed.append(t);b.Remove(t)
assert len(removed)==4
print('Supply groups after link removal:',len(groups('MODEM_3V8')),flush=True)
fps={f.GetReference():f for f in b.GetFootprints()}
a=next(d for d in fps['U1'].Pads()if d.GetNumber()=='40')
z=next(d for d in fps['C11'].Pads()if d.GetNumber()=='2')
change=route('GND',pos(a),pos(z),{0},{0},width=.16,step=.025,bounds=(50,12,57,20))
gs=groups('MODEM_3V8',add_track_anchors=True)
restoration=[]
if len(gs)>1:
    # C11/C12 remain real decoupling components; restore any disconnected link.
    os.environ['A18_ROUTE_VIA_DIAMETER_MM']='.45'
    for attempt in range(6):
        gs=groups('MODEM_3V8',add_track_anchors=True)
        if len(gs)<2:break
        import math
        pairs=sorted(((math.dist(pos(a),pos(z)),a,z)for a in gs[0]for g in gs[1:]for z in g),key=lambda q:q[0])
        for _,a,z in pairs[:12]:
            try:
                q=route('MODEM_3V8',pos(a),pos(z),{i for i,l in enumerate(layers)if a.IsOnLayer(l)},
                    {i for i,l in enumerate(layers)if z.IsOnLayer(l)},width=.375,step=.05)
                restoration.append(q);break
            except RuntimeError:pass
        else:break
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
native=out/'modem-ground-native.json'
subprocess.run([str(root/'build/cad-tools/kicad/bin/kicad-cli.exe'),'pcb','drc','--format','json','--output',str(native),str(FILE)],check=True,capture_output=True)
r=json.loads(native.read_text(encoding='utf-8'))
after={net:len(groups(net))for net in before}
hard=[v for v in r['violations']if v['type']not in('track_dangling','via_dangling')]
ok=not hard and all(after[n]<=before[n]for n in before)
report={'accepted_into_isolated_trial':ok,'protected_groups_before':before,'protected_groups_after':after,
    'ground_route':change,'decoupling_link_restoration':restoration,'native_unconnected':len(r['unconnected_items']),
    'native_findings':len(r['violations']),'hard':hard}
(out/'modem-ground-review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
if not ok:shutil.copy2(snapshot/FILE.name,FILE)
for t in removed:t.thisown=False
