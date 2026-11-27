"""Merge explicitly selected added copper, retaining the latest target edits.

No replacement of target footprints, net definitions, rules or existing
copper. Require native improvement and no new hard finding or pad disconnect.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from comparison_route_geometry import b, FILE, p
from repair_comparison_groups import groups

source = Path(os.environ['A18_ADDED_COPPER_SOURCE']).resolve()
selected = set(filter(None, os.environ['A18_ADDED_COPPER_NETS'].split(',')))
assert selected and source != FILE
repo = Path(__file__).resolve().parents[2]
assert source.is_relative_to(repo/'hardware')
extract = r'''
import sys,json,pcbnew as p
b=p.LoadBoard(sys.argv[1]);out=[]
for t in b.GetTracks():
 q={'net':t.GetNetname(),'uuid':t.m_Uuid.AsString(),'via':isinstance(t,p.PCB_VIA)}
 if q['via']:q.update(x=t.GetPosition().x,y=t.GetPosition().y,width=t.GetWidth(p.F_Cu),drill=t.GetDrill())
 else:q.update(ax=t.GetStart().x,ay=t.GetStart().y,zx=t.GetEnd().x,zy=t.GetEnd().y,width=t.GetWidth(),layer=t.GetLayer())
 out.append(q)
print(json.dumps(out))
'''
records = json.loads(subprocess.run([sys.executable,'-c',extract,str(source)],check=True,capture_output=True,text=True).stdout)
existing = {t.m_Uuid.AsString() for t in b.GetTracks()}
def geometry_key(q):
    if q['via']:
        return (q['net'], True, q['x'], q['y'], q['width'], q['drill'])
    endpoints = tuple(sorted(((q['ax'], q['ay']), (q['zx'], q['zy']))))
    return (q['net'], False, endpoints, q['width'], q['layer'])
target_records = json.loads(subprocess.run(
    [sys.executable, '-c', extract, str(FILE)], check=True,
    capture_output=True, text=True).stdout)
existing_geometry = {geometry_key(q) for q in target_records}
additions = [q for q in records if q['net'] in selected
             and q['uuid'] not in existing and geometry_key(q) not in existing_geometry]
assert additions
out = FILE.parent/'iterations'/('added-copper-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)
shutil.copy2(FILE,out/('before-'+FILE.name))
probe = out/FILE.name
for suffix in ('.kicad_pro','.kicad_dru'):
    shutil.copy2(FILE.with_suffix(suffix),probe.with_suffix(suffix))
for name in ('fp-lib-table','sym-lib-table'):
    (out/name).write_text((FILE.parent/name).read_text(encoding='utf-8').replace('${KIPRJMOD}',FILE.parent.as_posix()),encoding='utf-8')
cli=repo/'build/cad-tools/kicad/bin/kicad-cli.exe'
def check():
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(probe),b)
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(out/'drc.json'),str(probe)],check=True,capture_output=True)
    return json.loads((out/'drc.json').read_text(encoding='utf-8'))
baseline=check()
before={net:len(groups(net)) for net in selected}
added=[]
for q in additions:
    if q['via']:
        t=p.PCB_VIA(b);t.SetPosition(p.VECTOR2I(q['x'],q['y']))
        t.SetWidth(q['width']);t.SetDrill(q['drill']);t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetViaType(p.VIATYPE_THROUGH)
    else:
        t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(q['ax'],q['ay']));t.SetEnd(p.VECTOR2I(q['zx'],q['zy']))
        t.SetWidth(q['width']);t.SetLayer(q['layer'])
    t.SetNetCode(b.FindNet(q['net']).GetNetCode());b.Add(t);added.append(t)
candidate=check()
hard=[v for v in candidate['violations']if v['type'] not in ('track_dangling','via_dangling')]
after={net:len(groups(net)) for net in selected}
accepted=(not hard and len(candidate['unconnected_items'])<len(baseline['unconnected_items'])
          and all(after[net]<=before[net]for net in selected))
if accepted:p.SaveBoard(str(FILE),b)
else:
    for t in added:b.Remove(t);t.thisown=False
report={'source':str(source),'selected_nets':sorted(selected),'added_items':len(additions),'accepted':accepted,
        'pad_groups_before':before,'pad_groups_after':after,
        'native_unconnected':[len(baseline['unconnected_items']),len(candidate['unconnected_items'])],
        'native_findings':[len(baseline['violations']),len(candidate['violations'])],'hard_findings':hard}
(FILE.parent/'exports/added-copper-merge.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
