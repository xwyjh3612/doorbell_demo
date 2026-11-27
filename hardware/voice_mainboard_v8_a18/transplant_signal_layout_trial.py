"""Transplant named ordinary signals and named part positions into a trial.

Keep every other copper item, component identity, pin contract and rule.
Require native improvement and no worse physical pad connectivity on ANY net.
This script operates on an isolated target trial; final acceptance is separate.
"""
import collections
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from comparison_route_geometry import b, FILE, p, pos
from repair_comparison_groups import groups
from route_net_classes import PROTECTED

source = Path(os.environ['A18_SIGNAL_LAYOUT_SOURCE']).resolve()
selected = set(filter(None, os.environ['A18_SIGNAL_LAYOUT_NETS'].split(',')))
moved = set(filter(None, os.environ.get('A18_SIGNAL_LAYOUT_MOVED_REFS', '').split(',')))
assert selected and not selected.intersection(PROTECTED)
assert source != FILE
root = Path(__file__).resolve().parents[2]
assert FILE.is_relative_to(root/'hardware') and source.is_relative_to(root/'hardware')
for suffix in ('.kicad_pro', '.kicad_dru'):
    assert FILE.with_suffix(suffix).read_bytes() == source.with_suffix(suffix).read_bytes()
extract = r'''
import sys,json,pcbnew as p
b=p.LoadBoard(sys.argv[1]);parts={};copper=[]
for f in b.GetFootprints():
 parts[f.GetReference()]={'value':f.GetValue(),'fpid':[str(f.GetFPID().GetLibNickname()),str(f.GetFPID().GetLibItemName())],
 'pads':sorted((d.GetNumber(),d.GetNetname())for d in f.Pads()),
 'x':f.GetPosition().x,'y':f.GetPosition().y,'angle':f.GetOrientationDegrees(),'layer':f.GetLayer()}
for t in b.GetTracks():
 q={'net':t.GetNetname(),'via':isinstance(t,p.PCB_VIA),'locked':t.IsLocked()}
 if q['via']:q.update(x=t.GetPosition().x,y=t.GetPosition().y,width=t.GetWidth(p.F_Cu),drill=t.GetDrill(),kind=t.GetViaType())
 else:q.update(ax=t.GetStart().x,ay=t.GetStart().y,zx=t.GetEnd().x,zy=t.GetEnd().y,width=t.GetWidth(),layer=t.GetLayer())
 copper.append(q)
print(json.dumps({'parts':parts,'copper':copper}))
'''
data = json.loads(subprocess.run([sys.executable, '-c', extract, str(source)],
    check=True, capture_output=True, text=True).stdout)
parts = {f.GetReference(): f for f in b.GetFootprints()}
assert parts.keys() == data['parts'].keys()
for ref, f in parts.items():
    q = data['parts'][ref]
    fpid=[str(f.GetFPID().GetLibNickname()),str(f.GetFPID().GetLibItemName())]
    assert f.GetValue() == q['value'] and fpid == q['fpid'], ref
    assert sorted((d.GetNumber(),d.GetNetname()) for d in f.Pads()) == [tuple(a) for a in q['pads']], ref
for ref in moved:
    assert parts[ref].GetLayer() == data['parts'][ref]['layer'], 'Side changes require separate review'

out = FILE.parent/'iterations'/('signal-transplant-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)
shutil.copy2(FILE, out/FILE.name)
cli = root/'build/cad-tools/kicad/bin/kicad-cli.exe'
def check(name):
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    dest = out/(name+'-drc.json')
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(dest),str(FILE)],
        check=True,capture_output=True)
    return json.loads(dest.read_text(encoding='utf-8'))
nets = set(d.GetNetname() for f in b.GetFootprints() for d in f.Pads() if d.GetNetname())
before = {n:len(groups(n)) for n in nets}
base = check('before')
held = []
for t in list(b.GetTracks()):
    if t.GetNetname() in selected:
        b.Remove(t);held.append(t)
for ref in moved:
    q=data['parts'][ref];f=parts[ref]
    f.SetPosition(p.VECTOR2I(q['x'],q['y']));f.SetOrientationDegrees(q['angle'])
for q in data['copper']:
    if q['net'] not in selected:continue
    if q['via']:
        t=p.PCB_VIA(b);t.SetPosition(p.VECTOR2I(q['x'],q['y']))
        t.SetWidth(q['width']);t.SetDrill(q['drill']);t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetViaType(q['kind'])
    else:
        t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(q['ax'],q['ay']));t.SetEnd(p.VECTOR2I(q['zx'],q['zy']))
        t.SetWidth(q['width']);t.SetLayer(q['layer'])
    t.SetNetCode(b.FindNet(q['net']).GetNetCode());t.SetLocked(q['locked']);b.Add(t)
candidate=check('candidate')
p.SaveBoard(str(out/('candidate-'+FILE.name)),b)
after={n:len(groups(n)) for n in nets}
worse={n:[before[n],after[n]] for n in nets if after[n]>before[n]}
hard=[v for v in candidate['violations'] if v['type'] not in ('track_dangling','via_dangling')]
accepted=(not hard and not worse
          and len(candidate['unconnected_items'])<len(base['unconnected_items'])
          and len(candidate['violations'])<=len(base['violations']))
if accepted:
    path=FILE.parent/'design.json';design=json.loads(path.read_text(encoding='utf-8'))
    for q in design['parts']:
        if q['ref'] in moved:
            f=parts[q['ref']];q.update(x=pos(f)[0],y=pos(f)[1],angle=f.GetOrientationDegrees())
    path.write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
else:
    shutil.copy2(out/FILE.name,FILE)
for t in held:t.thisown=False
report={'accepted_into_isolated_trial':accepted,'source':str(source),'nets':sorted(selected),
    'moved_refs':sorted(moved),'native_unconnected':[len(base['unconnected_items']),len(candidate['unconnected_items'])],
    'native_findings':[len(base['violations']),len(candidate['violations'])],
    'hard_findings':hard,'worsened_pad_groups':worse,
    'improved_pad_groups':{n:[before[n],after[n]] for n in nets if after[n]<before[n]}}
(FILE.parent/'exports/signal-transplant.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
