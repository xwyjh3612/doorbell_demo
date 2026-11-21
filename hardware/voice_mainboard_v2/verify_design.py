"""Independent KiCad netlist-to-pad comparison and honest draft validation."""
from pathlib import Path
import json, xml.etree.ElementTree as ET
import pcbnew as pcb
ROOT=Path(__file__).resolve().parent
PROJECT='voice_mainboard_v2'
d=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
b=pcb.LoadBoard(str(ROOT/(PROJECT+'.kicad_pcb')))
expected={(p['ref'],n):name for p in d['parts'] for n,name in p['pins'].items() if name}
actual={(f.GetReference(),p.GetNumber()):p.GetNetname() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()}
assert expected==actual,'PCB pad-net mapping mismatch'
xml=ET.parse(ROOT/'exports'/f'{PROJECT}.net.xml').getroot()
sch={}
for net in xml.findall('./nets/net'):
    name=net.attrib['name'].removeprefix('/')
    for node in net.findall('node'):
        if not node.attrib['ref'].startswith('#') and not name.startswith('unconnected-'):
            sch[(node.attrib['ref'],node.attrib['pin'])]=name
assert expected==sch,{'missing':list(set(expected.items())-set(sch.items())),'extra':list(set(sch.items())-set(expected.items()))}
erc=json.loads((ROOT/'exports/erc.json').read_text(encoding='utf-8'))
drc=json.loads((ROOT/'exports/placement-drc.json').read_text(encoding='utf-8'))
ev=[v for sheet in erc['sheets'] for v in sheet['violations']]
assert not ev,'Schematic ERC failures'
assert not drc['violations'],'Placement DRC failures'
module=next(f for f in b.GetFootprints() if f.GetReference()=='U1')
assert len(list(module.Pads()))==109
assert len({p.GetNumber() for p in module.Pads()})==109
ids=json.loads((ROOT/'schematic-ids.json').read_text(encoding='utf-8'))
for f in b.GetFootprints():
    if f.GetReference() in ids['symbols']:
        path=pcb.KIID_PATH();path.push_back(pcb.KIID(ids['root']));path.push_back(pcb.KIID(ids['symbols'][f.GetReference()]));f.SetPath(path)
pcb.SaveBoard(str(ROOT/(PROJECT+'.kicad_pcb')),b)
report={'revision':d['revision'],'kicad_version':pcb.Version(),'electrical_parts':len([p for p in d['parts'] if p['kind']!='mechanical']),
 'ml307_pad_count':109,'connected_unique_pin_net_mappings':len(expected),'netlist_matches_pcb':True,'schematic_erc_violations':len(ev),
 'placement_drc_violations':len(drc['violations']),'unrouted_links':len(drc['unconnected_items']),
 'manufacturing_ready':False,'rf_routed':False,'usb_routed':False,'ups_chip_frozen':False,'supplier_ml307_footprint_signoff':False,
 'mechanical_fit_verified':False,'full_power_simulation':False,'physical_electrical_tests':False,'firmware_modified':False}
(ROOT/'exports/validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
