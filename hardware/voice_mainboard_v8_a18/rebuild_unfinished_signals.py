"""Retire obsolete routes on explicitly selected unfinished ordinary nets.

All footprints, pad locations, pad nets, manufacturing rules and protected
power/RF/speaker copper are preserved. The snapshot permits a complete undo.
This creates routing work; it must never be presented as a checked PCB.
"""
import datetime
import json
import os
import shutil

from comparison_route_geometry import b, FILE, p
from repair_comparison_groups import groups
from route_net_classes import PROTECTED

selected=set(filter(None,os.environ['A18_REBUILD_SIGNAL_NETS'].split(',')))
assert selected and not selected.intersection(PROTECTED)
selected={net for net in selected if len(groups(net))>1}
assert selected
snapshot=FILE.parent/'iterations'/('before-signal-rebuild-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE,snapshot/FILE.name)
contract=lambda:sorted((f.GetReference(),d.GetNumber(),d.GetNetname(),d.GetPosition().x,d.GetPosition().y)
                      for f in b.GetFootprints() for d in f.Pads())
before=contract()
removed=[];held=[]
for t in list(b.GetTracks()):
    if t.GetNetname() in selected:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'via':isinstance(t,p.PCB_VIA)})
        b.Remove(t);held.append(t)
assert before==contract()
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
report={'selected_unfinished_nets':sorted(selected),'retired_copper':removed,'snapshot':str(snapshot),
        'pads_nets_rules_changed':False,'status':'Routing incomplete; native checks required'}
(FILE.parent/'exports/signal-rebuild.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Retired obsolete unfinished signal routes:',len(removed),'items on',len(selected),'nets',flush=True)
