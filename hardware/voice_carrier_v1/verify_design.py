"""Compare independently exported KiCad nets to PCB pads; report draft readiness.

Run with KiCad Python after generating schematic netlist and DRC/ERC JSON.
The report explicitly retains unrouted links; ERC success is not a power test.
"""
from pathlib import Path
import json, xml.etree.ElementTree as ET
import pcbnew as pcb
ROOT=Path(__file__).resolve().parent
d=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
b=pcb.LoadBoard(str(ROOT/'voice_carrier_v1.kicad_pcb'))
expected={(p['ref'],n):name for p in d['parts'] for n,name in p['pins'].items() if name}
actual={(f.GetReference(),p.GetNumber()):p.GetNetname() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()}
assert expected==actual, 'PCB pad/net mismatch'
xml=ET.parse(ROOT/'exports/voice_carrier_v1.net.xml').getroot()
sch={}
for net in xml.findall('./nets/net'):
    name=net.attrib['name'].removeprefix('/')
    for p in net.findall('node'):
        if not p.attrib['ref'].startswith('#') and not name.startswith('unconnected-'):
            sch[(p.attrib['ref'],p.attrib['pin'])]=name
assert expected==sch, {'missing':list(set(expected.items())-set(sch.items())),'extra':list(set(sch.items())-set(expected.items()))}
erc=json.loads((ROOT/'exports/erc.json').read_text(encoding='utf-8'))
drc=json.loads((ROOT/'exports/placement-drc.json').read_text(encoding='utf-8'))
violations=[v for s in erc['sheets'] for v in s['violations']]
assert not violations, 'Schematic ERC violations'
assert not drc['violations'], 'Placement geometry violations'
ids=json.loads((ROOT/'schematic-ids.json').read_text(encoding='utf-8'))
for f in b.GetFootprints():
    ref=f.GetReference()
    if ref in ids['symbols']:
        path=pcb.KIID_PATH();path.push_back(pcb.KIID(ids['root']));path.push_back(pcb.KIID(ids['symbols'][ref]));f.SetPath(path)
pcb.SaveBoard(str(ROOT/'voice_carrier_v1.kicad_pcb'),b)
cost=sum(p['price'] for p in d['parts'] if p['kind']!='mechanical')
report={'revision':d['revision'],'kicad_version':pcb.Version(),'electrical_components':len([p for p in d['parts'] if p['kind']!='mechanical']),
 'mechanical_holes':4,'named_nets':len(set(expected.values())),'connected_pin_map_matches':len(expected),
 'schematic_erc_violations':len(violations),'placement_geometry_violations':len(drc['violations']),
 'unrouted_links':len(drc['unconnected_items']),'pcb_material_reference_cny':round(cost,4),
 'manufacturing_ready':False,'power_tested':False,'module_fit_verified':False,
 'status':'Net-labelled schematic and unrouted placement draft. Complete power layout, mechanical check and electrical validation before fabrication.'}
(ROOT/'exports/validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
