"""Rebuild the three mux supply rails and its controls in the new placement.

Keeps every pad/net, all ground copper and the reviewed converter switch/output
networks. Existing signal geometry is preserved for subsequent native repair.
"""
import datetime
import hashlib
import json
import os
import shutil

from comparison_route_geometry import b, FILE, p

nets={'SYS_5V','VIN_PROTECTED','BAT_BOOST_5V','UPS_PR1','SUPPLY_BAT_N47'}
if os.environ.get('A18_RESET_MUX_NETS'):
    selected=set(os.environ['A18_RESET_MUX_NETS'].split(','))
    assert selected<=nets
    nets=selected
snapshot=FILE.parent/'iterations'/('before-mux-rail-rebuild-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
for path in [FILE,FILE.with_suffix('.kicad_sch'),FILE.with_suffix('.kicad_pro'),FILE.parent/'design.json']:
    shutil.copy2(path,snapshot/path.name)
contract=lambda:sorted((f.GetReference(),d.GetNumber(),d.GetNetname(),d.GetPosition().x,d.GetPosition().y)
                       for f in b.GetFootprints() for d in f.Pads())
before=contract();held=[];removed=[]
for t in list(b.GetTracks()):
    if t.GetNetname() in nets:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'via':isinstance(t,p.PCB_VIA)})
        b.Remove(t);held.append(t)
assert contract()==before
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
report={'reset_nets':sorted(nets),'removed_copper':removed,'pad_or_rule_changes':False,
        'snapshot':str(snapshot),'status':'Routes must be rebuilt; not a manufacturing release',
        'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest()}
(FILE.parent/'exports/mux-rail-rebuild.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Reset mux rails and controls only:',len(removed),'copper items; all pads and converter loops retained')
