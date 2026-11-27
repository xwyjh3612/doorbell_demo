"""Accept the explicitly equivalent R75/R76 copper straps after native checks.

Unlike ordinary layout acceptance, this permits exactly two existing zero-ohm
straps to be removed. Compare the complete schematic netlist after contracting
those shorts; all remaining parts, pads, geometry, rules and protected nets
must retain their original contracts. No firmware or DRC exclusions change.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
target = Path(os.environ['A18_ACCEPT_TARGET']).resolve()
trial = Path(os.environ['A18_ACCEPT_TRIAL']).resolve()
assert target != trial
assert all(p.is_relative_to(root/'hardware') for p in [target, trial])
cli = root/'build/cad-tools/kicad/bin/kicad-cli.exe'
out = target.parent/'iterations'/('accepted-fixed-audio-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True)
for suffix in ['.kicad_pcb', '.kicad_sch', '.kicad_pro', '.kicad_dru']:
    shutil.copy2(target.with_suffix(suffix), out/target.with_suffix(suffix).name)
    if suffix in ['.kicad_pro', '.kicad_dru']:
        assert target.with_suffix(suffix).read_bytes() == trial.with_suffix(suffix).read_bytes()
shutil.copy2(target.parent/'design.json', out/'design.json')
removed = {'R75', 'R76'}
merged = {'AMP_GAIN':'GND', 'AMP_SD':'SYS_5V'}
extract = r'''
import sys,json
sys.path.insert(0,sys.argv[1])
from comparison_route_geometry import b,pos
from repair_comparison_groups import groups
from route_net_classes import PROTECTED
print(json.dumps({'layers':b.GetCopperLayerCount(),
 'parts':{f.GetReference():{'id':[str(f.GetFPID().GetLibNickname()),str(f.GetFPID().GetLibItemName())],'value':f.GetValue(),
 'position':[*pos(f),f.GetOrientationDegrees(),f.GetLayer()],
 'pads':{d.GetNumber():[d.GetNetname(),*pos(d),d.GetSize().x,d.GetSize().y,d.GetDrillSize().x,d.GetDrillSize().y] for d in f.Pads()}}
 for f in b.GetFootprints()},
 'protected_groups':{n:len(groups(n)) for n in PROTECTED if b.FindNet(n)},
 'audio_groups':len(groups('I2S_SPK_DATA7'))}))
'''
def inspect(board):
    p = subprocess.run([sys.executable,'-c',extract,str(Path(__file__).parent)],
        env=dict(os.environ,A18_REPAIR_BOARD=str(board)),capture_output=True,text=True,check=True)
    return json.loads(p.stdout)
before, after = inspect(target), inspect(trial)
assert before['layers'] == after['layers'] == 2
assert set(before['parts']) - set(after['parts']) == removed
assert not set(after['parts']) - set(before['parts'])
assert all(before['parts'][r]['value'].startswith('0R') for r in removed)
assert {n:v[0] for n,v in before['parts']['R75']['pads'].items()} == {'1':'SYS_5V','2':'AMP_SD'}
assert {n:v[0] for n,v in before['parts']['R76']['pads'].items()} == {'1':'AMP_GAIN','2':'GND'}
for ref, candidate in after['parts'].items():
    old = json.loads(json.dumps(before['parts'][ref]))
    if ref == 'U14':
        assert old['pads']['2'][0] == 'AMP_GAIN' and old['pads']['4'][0] == 'AMP_SD'
        old['pads']['2'][0] = 'GND'
        old['pads']['4'][0] = 'SYS_5V'
    assert old == candidate, ref
assert before['protected_groups'] == after['protected_groups']
assert all(n == 1 for n in after['protected_groups'].values())
assert before['audio_groups'] == 2 and after['audio_groups'] == 1

def netlist(board, name):
    file = out/(name+'-netlist.xml')
    subprocess.run([str(cli),'sch','export','netlist','--format','kicadxml','--output',str(file),str(board.with_suffix('.kicad_sch'))],check=True,capture_output=True)
    doc = ET.parse(file).getroot()
    comps = {c.attrib['ref']:(c.findtext('value'),c.findtext('footprint')) for c in doc.findall('./components/comp') if c.attrib['ref'] not in removed}
    pins = {}
    for net in doc.findall('./nets/net'):
        netname = merged.get(net.attrib['name'],net.attrib['name'])
        for node in net.findall('node'):
            if node.attrib['ref'] not in removed:
                key = (node.attrib['ref'],node.attrib['pin'])
                assert key not in pins
                pins[key] = netname
    return comps,pins
assert netlist(target,'before') == netlist(trial,'trial'), 'Schematic changed beyond the two contracted shorts'

def drc(board, name):
    file = out/(name+'-drc.json')
    subprocess.run([str(cli),'pcb','drc','--format','json','--schematic-parity','--output',str(file),str(board)],check=True,capture_output=True)
    return json.loads(file.read_text(encoding='utf-8'))
base, result = drc(target,'before'), drc(trial,'trial')
assert not result['violations'] and not result['schematic_parity']
assert len(result['unconnected_items']) < len(base['unconnected_items'])
ercfile = out/'trial-erc.json'
subprocess.run([str(cli),'sch','erc','--format','json','--output',str(ercfile),str(trial.with_suffix('.kicad_sch'))],check=True,capture_output=True)
erc = json.loads(ercfile.read_text(encoding='utf-8'))
assert not any(s.get('violations') for s in erc.get('sheets',[])), erc
for suffix in ['.kicad_pcb','.kicad_sch']:
    shutil.copy2(trial.with_suffix(suffix), target.with_suffix(suffix))
shutil.copy2(trial.parent/'design.json', target.parent/'design.json')
report = {'trial':str(trial),'equivalent_zero_ohm_removal':sorted(removed),
    'gain_db':12,'audio_channel':'left','full_contracted_schematic_netlist_equal':True,
    'native_unconnected':[len(base['unconnected_items']),len(result['unconnected_items'])],
    'native_violations':[len(base['violations']),len(result['violations'])],
    'protected_groups':after['protected_groups'],'ERC_violations':0,'schematic_parity':0,
    'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'snapshot':str(out),
    'manufacturing_ready':False}
(target.parent/'exports/accepted-local-layout.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(target.parent/'exports/accepted-fixed-audio.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
