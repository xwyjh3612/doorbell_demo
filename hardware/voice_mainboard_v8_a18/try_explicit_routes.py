"""Validate explicitly planned local tracks against native KiCad rules.

Only a named MODE logic-neck repair can retire narrow VIN branch segments.
Its main VIN1 copper path and pad connectivity must survive every accepted
change. No required pads, nets or design rules can be removed.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

from comparison_route_geometry import b, FILE, p
from repair_comparison_groups import groups
from audit_copper_paths import trace_path

repo=Path(__file__).resolve().parents[2]
cli=repo/'build/cad-tools/kicad/bin/kicad-cli.exe'
out=FILE.parent/'iterations'/('explicit-routes-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)
shutil.copy2(FILE,out/('before-'+FILE.name))
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
def hard(report):
    return [q for q in report['violations'] if q['type'] not in ['track_dangling','via_dangling']]
def non_ground_airwires(report):
    return [q for q in report['unconnected_items']
            if not any('[GND]' in item['description'] for item in q['items'])]
report=check();assert not hard(report)
log=[];held=[]
for plan in json.loads(os.environ['A18_EXPLICIT_ROUTE_PLANS']):
    before=report
    before_groups=len(groups(plan['net']))
    before_vin=trace_path(('Q6',2),('U18',3))
    added=[];retired=[]
    layer=p.F_Cu if plan['layer']=='F' else p.B_Cu
    assert plan['width']>=.16
    for a,z in zip(plan['points'],plan['points'][1:]):
        t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])))
        t.SetEnd(p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1])))
        t.SetLayer(layer);t.SetWidth(p.FromMM(plan['width']))
        t.SetNetCode(b.FindNet(plan['net']).GetNetCode());t.SetLocked(True);b.Add(t);added.append(t)
    if plan.get('via'):
        q=plan['via'];xy=plan['points'][-1]
        assert q['diameter']>=q['drill']+.2-1e-9
        t=p.PCB_VIA(b);t.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
        t.SetWidth(p.FromMM(q['diameter']));t.SetDrill(p.FromMM(q['drill']))
        t.SetViaType(p.VIATYPE_THROUGH);t.SetLayerPair(p.F_Cu,p.B_Cu)
        t.SetNetCode(b.FindNet(plan['net']).GetNetCode());t.SetLocked(True);b.Add(t);added.append(t)
    candidate=check()
    if hard(candidate) and plan.get('repair_MODE_logic_neck'):
        assert plan['net']=='UPS_PR1'
        objects={t.m_Uuid.AsString():t for t in b.GetTracks()}
        selected={}
        for q in hard(candidate):
            for item in q['items']:
                t=objects.get(item['uuid'])
                if t is None or isinstance(t,p.PCB_VIA) or t in added:
                    continue
                pts=[t.GetStart(),t.GetEnd()]
                if (t.GetNetname()=='VIN_PROTECTED' and t.GetLayer()==p.B_Cu
                    and p.ToMM(t.GetWidth())<=.251 and not t.IsLocked()
                    and all(65<=p.ToMM(q.x)<=69 and 47.5<=p.ToMM(q.y)<=49.3 for q in pts)):
                    selected[t.m_Uuid.AsString()]=t
        for t in selected.values():
            b.Remove(t);retired.append(t)
        candidate=check()
    vin=trace_path(('Q6',2),('U18',3))
    vin_ok=not retired or (len(groups('VIN_PROTECTED'))==1 and vin['trace_graph_connected']
                            and vin['estimated_R_20C_ohm']<=max(.04,before_vin.get('estimated_R_20C_ohm',0)+.001))
    connectivity_ok=len(candidate['unconnected_items'])<=len(before['unconnected_items'])
    if plan.get('allow_ground_repour_disconnect'):
        assert plan.get('via'), 'Ground repour allowance is for unfinished escape planning only'
        connectivity_ok=len(non_ground_airwires(candidate))<=len(non_ground_airwires(before))
    accepted=(not hard(candidate) and connectivity_ok
              and len(groups(plan['net']))<=before_groups and vin_ok)
    entry={'plan':plan,'accepted':accepted,'hard_findings':hard(candidate),
           'native_unconnected':len(candidate['unconnected_items']),
           'non_ground_unconnected_before':len(non_ground_airwires(before)),
           'non_ground_unconnected_after':len(non_ground_airwires(candidate)),
           'retired_MODE_neck_items':[t.m_Uuid.AsString() for t in retired],
           'VIN1_path_after':vin}
    log.append(entry)
    if accepted:
        report=candidate;held.extend(retired);p.SaveBoard(str(FILE),b)
    else:
        for t in added:b.Remove(t);held.append(t)
        for t in retired:b.Add(t)
        b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
    print(plan.get('purpose',plan['net']),':', 'accepted' if accepted else 'rolled back',
          '; hard findings:',len(hard(candidate)),'; native unconnected:',len(candidate['unconnected_items']),flush=True)
(FILE.parent/'exports/explicit-route-review.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
for t in held:t.thisown=False
