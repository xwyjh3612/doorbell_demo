"""Accept a named layout trial only after independent native and pad checks.

Supports explicitly moved parts. Net contracts, component identity, protected
copper connectivity, project rules and copper layers must remain unchanged.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
target = Path(os.environ['A18_ACCEPT_TARGET']).resolve()
trial = Path(os.environ['A18_ACCEPT_TRIAL']).resolve()
allowed = set(filter(None, os.environ.get('A18_ACCEPT_MOVED_REFS', '').split(',')))
via_policy=os.environ.get('A18_ACCEPT_SIGNAL_VIA_MIN')
widths_only=os.environ.get('A18_ACCEPT_POWER_WIDTHS_ONLY')=='1'
connector_access=os.environ.get('A18_ACCEPT_CONNECTOR_ACCESS')=='1'
power_paths=os.environ.get('A18_ACCEPT_POWER_PATHS')=='1'
assert sum([widths_only,connector_access,power_paths])<=1
policy_change=None
if via_policy:
    # A named fabrication process change, rather than an ignored DRC finding.
    # Keep annular ring, drill, clearance and every other setting identical.
    assert via_policy=='0.4'
    old=json.loads(target.with_suffix('.kicad_pro').read_text(encoding='utf-8'))
    new=json.loads(trial.with_suffix('.kicad_pro').read_text(encoding='utf-8'))
    oldrules=old['board']['design_settings']['rules'];newrules=new['board']['design_settings']['rules']
    assert oldrules['min_via_diameter']==.45 and newrules['min_via_diameter']==.4
    assert newrules['min_via_annular_width']>=.1 and newrules['min_through_hole_diameter']>=.2
    normalized=json.loads(json.dumps(new));normalized['board']['design_settings']['rules']['min_via_diameter']=.45
    assert old==normalized,'Only the documented signal via minimum may change'
    policy=json.loads((trial.parent/'exports/signal-via-manufacturing-policy.json').read_text(encoding='utf-8'))
    assert policy['via_outer_diameter_mm']==.4 and policy['drill_mm']==.2 and policy['annular_ring_mm']==.1
    assert policy['extra_fabrication_charge_possible'] is True
    assert policy['source_url']=='https://jlcpcb.com/capabilities/pcb-capabilities'
    policy_change={'minimum_via_diameter_mm':[.45,.4],'annular_ring_mm':.1,'drill_mm':.2,
        'source_url':policy['source_url'],'extra_fabrication_charge_possible':True}
assert target.is_relative_to(root / 'hardware') and trial.is_relative_to(root / 'hardware')
assert target != trial
cli = root / 'build/cad-tools/kicad/bin/kicad-cli.exe'
snapshot = target.parent / 'iterations' / ('accepted-local-layout-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
for suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_dru'):
    assert suffix == '.kicad_pcb' or (suffix=='.kicad_pro' and policy_change) or target.with_suffix(suffix).read_bytes() == trial.with_suffix(suffix).read_bytes()
    shutil.copy2(target.with_suffix(suffix), snapshot / target.with_suffix(suffix).name)
shutil.copy2(target.parent / 'design.json', snapshot / 'design.json')
shutil.copy2(target.with_suffix('.kicad_sch'), snapshot / target.with_suffix('.kicad_sch').name)
assert target.with_suffix('.kicad_sch').read_bytes() == trial.with_suffix('.kicad_sch').read_bytes(), 'Ordinary layout acceptance cannot change the schematic'
extract = r'''
import sys,json,os
sys.path.insert(0,sys.argv[2])
from comparison_route_geometry import b,pos,p
from repair_comparison_groups import groups
from route_net_classes import PROTECTED
print(json.dumps({'layers':b.GetCopperLayerCount(),
 'parts':{f.GetReference():{'id':[str(f.GetFPID().GetLibNickname()),str(f.GetFPID().GetLibItemName())],'value':f.GetValue(),
 'position':[*pos(f),f.GetOrientationDegrees(),f.GetLayer()],
 'pads':sorted((d.GetNumber(),d.GetNetname()) for d in f.Pads())} for f in b.GetFootprints()},
 'protected_groups':{n:len(groups(n)) for n in PROTECTED if b.FindNet(n)},
 # Monotonic widening cannot disconnect a track/pad-only net. Refilled zone
 # nets can change, so independently inspect every actual non-rule-area zone.
 'all_groups':{n:len(groups(n)) for n in ({d.GetNetname()for f in b.GetFootprints()for d in f.Pads()} if os.environ.get('A18_ACCEPT_CONNECTOR_ACCESS')=='1' or os.environ.get('A18_ACCEPT_POWER_PATHS')=='1' else {z.GetNetname()for z in b.Zones()if not z.GetIsRuleArea()})if n} if os.environ.get('A18_ACCEPT_POWER_WIDTHS_ONLY')=='1' or os.environ.get('A18_ACCEPT_CONNECTOR_ACCESS')=='1' or os.environ.get('A18_ACCEPT_POWER_PATHS')=='1' else {},
 'tracks':{t.m_Uuid.AsString():{'net':t.GetNetname(),'layer':t.GetLayer(),
 'start':[t.GetStart().x,t.GetStart().y],'end':[t.GetEnd().x,t.GetEnd().y],
 'width':t.GetWidth(p.F_Cu)if isinstance(t,p.PCB_VIA)else t.GetWidth(), 'drill':t.GetDrill()if isinstance(t,p.PCB_VIA)else None,
 'via':isinstance(t,p.PCB_VIA)}for t in b.GetTracks()}if os.environ.get('A18_ACCEPT_POWER_WIDTHS_ONLY')=='1'else {}}))
'''
def inspect(board):
    env = dict(os.environ, A18_REPAIR_BOARD=str(board))
    data = subprocess.run([sys.executable, '-c', extract, str(board), str(Path(__file__).parent)],
                          env=env, capture_output=True, text=True)
    if data.returncode:
        print(data.stderr)
        data.check_returncode()
    return json.loads(data.stdout)
before, after = inspect(target), inspect(trial)
assert before['layers'] == after['layers'] == 2
assert before['parts'].keys() == after['parts'].keys()
for ref, part in before['parts'].items():
    candidate = after['parts'][ref]
    assert (part['pads'], part['value'], part['id']) == (candidate['pads'], candidate['value'], candidate['id']), ref
    assert ref in allowed or part['position'] == candidate['position'], ref
assert before['protected_groups'] == after['protected_groups'], 'Protected rail/ground connectivity changed'
power_comparison=[]
if power_paths:
    assert not allowed, 'Power shortcut acceptance cannot move any component'
    assert before['all_groups']==after['all_groups'], 'Power shortcut changed pad groups'
    def paths(board):
        env=dict(os.environ,A18_REPAIR_BOARD=str(board))
        subprocess.run([sys.executable,str(Path(__file__).parent/'audit_copper_paths.py')],env=env,capture_output=True,check=True)
        audit=json.loads((board.parent/'exports/copper-path-audit.json').read_text(encoding='utf-8'))
        assert audit['PCB_sha256']==hashlib.sha256(board.read_bytes()).hexdigest()
        return {(q['net'],tuple(q['from']),tuple(q['to'])):q for q in audit['paths']}
    oldpaths,newpaths=paths(target),paths(trial)
    assert oldpaths.keys()==newpaths.keys()
    for key,old in oldpaths.items():
        new=newpaths[key]
        if old['trace_graph_connected']:
            assert new['trace_graph_connected'],key
            assert new['estimated_R_20C_ohm']<=old['estimated_R_20C_ohm']+1e-7,key
    old=oldpaths[('VIN_DC',('J1',4),('F1',1))]
    new=newpaths[('VIN_DC',('J1',4),('F1',1))]
    assert new['estimated_R_20C_ohm']<old['estimated_R_20C_ohm']
    assert new['estimated_drop_at_2A_V']<=.025
    assert new['minimum_width_mm_on_estimated_path']>=.6
    power_comparison={'input_path_before':old,'input_path_after':new,
        'all_existing_explicit_path_resistances_not_increased':True,
        'scope':'20C centreline copper estimate only; not dynamic/current/thermal qualification'}
if connector_access:
    assert allowed=={'J1','J15'}, 'Connector review may move only the jack and speaker header'
    assert before['all_groups']==after['all_groups'], 'A connector move cannot disconnect any pad group'
    # This is an explicit mechanical objective, independent of airwire count.
    # Preserve each connector's footprint/pin identity above and verify its
    # intended position rather than treating any 0-to-0 layout as acceptable.
    assert after['parts']['J1']['position']==[79.0,46.0,180.0,2]
    assert after['parts']['J15']['position']==[58.0,52.25,90.0,0]
    olddesign=json.loads((target.parent/'design.json').read_text(encoding='utf-8'))
    newdesign=json.loads((trial.parent/'design.json').read_text(encoding='utf-8'))
    access=newdesign['mechanical']['jack_access']
    assert access['nominal_face_recess_mm']==0 and access['component_overhang_mm']==6
    assert access['case_window_height_and_actual_wall_require_physical_verification'] is True
    assert olddesign['mechanical']['outline_mm']==newdesign['mechanical']['outline_mm']
width_changes=[]
if widths_only:
    assert before['all_groups']==after['all_groups'], 'Widening changed pad connectivity'
    assert before['tracks'].keys()==after['tracks'].keys(), 'Widening cannot add or remove copper'
    rails={'VIN_DC','VIN_FUSED','VIN_PROTECTED','SYS_5V','MODEM_3V8','BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','UPS_SW','BUCK_SW','ESP_SW'}
    for uid,old in before['tracks'].items():
        new=after['tracks'][uid]
        normalized=dict(new,width=old['width'])
        assert normalized==old, uid
        assert new['width']>=old['width'], uid
        if new['width']>old['width']:
            assert old['net']in rails and not old['via'], uid
            width_changes.append({'uuid':uid,'net':old['net'],'width_mm':[old['width']/1e6,new['width']/1e6]})
    assert width_changes, 'No power copper was widened'
def check(board, filename):
    subprocess.run([str(cli), 'pcb', 'drc', '--format', 'json', '--schematic-parity', '--output', str(filename), str(board)],
                   check=True, capture_output=True)
    return json.loads(filename.read_text(encoding='utf-8'))
base = check(target, snapshot / 'before-drc.json')
candidate = check(trial, snapshot / 'trial-drc.json')
hard = [v for v in candidate['violations'] if v['type'] not in ('track_dangling', 'via_dangling')]
assert not hard, hard
if connector_access or power_paths:
    assert not candidate['unconnected_items'] and not candidate['violations'] and not candidate['schematic_parity'], 'Connector revision requires native checks all zero'
else:
    assert len(candidate['unconnected_items']) <= len(base['unconnected_items']) if widths_only else len(candidate['unconnected_items']) < len(base['unconnected_items']), 'No native connectivity improvement'
assert len(candidate['violations']) <= len(base['violations'])
assert len(candidate['schematic_parity']) <= len(base['schematic_parity'])
shutil.copy2(trial, target)
if policy_change:
    shutil.copy2(trial.with_suffix('.kicad_pro'),target.with_suffix('.kicad_pro'))
    shutil.copy2(trial.parent/'exports/signal-via-manufacturing-policy.json',target.parent/'exports/signal-via-manufacturing-policy.json')
shutil.copy2(trial.parent / 'design.json', target.parent / 'design.json')
report = {'trial': str(trial), 'allowed_moved_parts': sorted(allowed),
          'native_unconnected': [len(base['unconnected_items']), len(candidate['unconnected_items'])],
          'native_violations': [len(base['violations']), len(candidate['violations'])],
          'protected_groups': after['protected_groups'], 'snapshot': str(snapshot),
          'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'manufacturing_ready': False}
if policy_change:report['documented_fabrication_process_change']=policy_change
if widths_only:report['verified_power_width_changes']=width_changes
if connector_access:report['verified_connector_access']={'nominal_jack_face_recess_mm':[6.75,0], 'all_pad_groups_unchanged':True, 'case_window_physical_verification_required':True}
if power_paths:report['verified_power_path_improvement']=power_comparison
(target.parent / 'exports/accepted-local-layout.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
