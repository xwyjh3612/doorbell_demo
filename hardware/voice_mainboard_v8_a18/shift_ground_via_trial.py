"""Try a nearby ground stitching location; native DRC and ground groups decide.

Keep the via dimensions, all pad nets and all other copper.
"""
import json
import os
from pathlib import Path
import subprocess
import pcbnew as p
from comparison_route_geometry import b,FILE
from repair_comparison_groups import groups

root=Path(__file__).resolve().parents[2]
original=FILE.read_bytes();records=[]
via=next(t for t in b.GetTracks()if t.m_Uuid.AsString()=='59bd67ab-ff32-4abd-a76e-d6cc4dd6caf8')
assert isinstance(via,p.PCB_VIA)and via.GetNetname()=='GND'
before=len(groups('GND'))
start=via.GetPosition()
for x,y in[(31.9,47.85),(31.85,47.85),(31.8,47.8),(31.9,47.9)]:
    via.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    dest=FILE.parent/'exports'/'ground-via-shift-native.json'
    subprocess.run([str(root/'build/cad-tools/kicad/bin/kicad-cli.exe'),'pcb','drc','--format','json','--output',str(dest),str(FILE)],check=True,capture_output=True)
    r=json.loads(dest.read_text(encoding='utf-8'));hard=[v for v in r['violations']if v['type']not in('via_dangling','track_dangling')]
    n=len(groups('GND'));records.append({'x':x,'y':y,'hard':hard,'ground_groups':n,'unconnected':len(r['unconnected_items'])})
    print('Ground via',x,y,'hard',len(hard),'groups',n,flush=True)
    if not hard and n<=before:break
else:FILE.write_bytes(original)
(FILE.parent/'exports'/'ground-via-shift-trials.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
