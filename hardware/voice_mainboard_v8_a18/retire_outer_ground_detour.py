"""Remove the old jack-to-debug-header edge detour only if pours retain pads.

That detour was not a model of the modem's actual supply return. Native ground
connectivity and all pad groups must survive. Current distribution and thermal
qualification of the real ground planes remain separate review tasks.
"""
import datetime
import json
import shutil
import subprocess
from pathlib import Path

from comparison_route_geometry import b, FILE, p
from repair_comparison_groups import groups

cli=Path(__file__).resolve().parents[2]/'build/cad-tools/kicad/bin/kicad-cli.exe'
out=FILE.parent/'exports'
snapshot=FILE.parent/'iterations'/('before-ground-detour-retirement-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True);shutil.copy2(FILE,snapshot/FILE.name)
def check():
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(out/'ground-detour-native.json'),str(FILE)],check=True,capture_output=True)
    return json.loads((out/'ground-detour-native.json').read_text(encoding='utf-8'))
before=check();before_groups=len(groups('GND'))
assert not [q for q in before['violations'] if q['type'] not in ['track_dangling','via_dangling']]
selected=[t for t in b.GetTracks() if not isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND'
          and t.IsLocked() and p.ToMM(t.GetWidth())>=.49
          and min(p.ToMM(t.GetStart().x),p.ToMM(t.GetEnd().x))>=61]
assert selected
records=[{'uuid':t.m_Uuid.AsString(),'width_mm':p.ToMM(t.GetWidth())} for t in selected]
for t in selected:b.Remove(t)
after=check()
accepted=(not [q for q in after['violations'] if q['type'] not in ['track_dangling','via_dangling']]
          and len(after['unconnected_items'])<=len(before['unconnected_items'])
          and len(groups('GND'))<=before_groups)
if not accepted:
    for t in selected:b.Add(t)
    after=check()
report={'accepted':accepted,'selected':records,'snapshot':str(snapshot),'ground_pad_groups_before':before_groups,
        'ground_pad_groups_after':len(groups('GND')),'unconnected_before':len(before['unconnected_items']),
        'unconnected_after':len(after['unconnected_items']),'ground_plane_current_qualified':False}
(out/'ground-detour-retirement.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if accepted:
    for t in selected:t.thisown=False
print(json.dumps(report),flush=True)
