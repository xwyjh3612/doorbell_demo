"""Independent XML-netlist/PCB/assembly verification of the saved V3 board."""
from pathlib import Path
import json,collections,hashlib,xml.etree.ElementTree as ET
import pcbnew as p
root=Path(__file__).resolve().parent
d=json.loads((root/'design.json').read_text(encoding='utf8'))
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
expected={(x['ref'],n):net for x in d['parts'] for n,net in x['pins'].items() if net}
actual={(f.GetReference(),pd.GetNumber()):pd.GetNetname() for f in b.GetFootprints() for pd in f.Pads() if pd.GetNetname()}
assert expected==actual,'Saved PCB pin/net contract differs'
xml=ET.parse(root/'exports/voice_mainboard_v3.net.xml').getroot();sch={}
for net in xml.findall('./nets/net'):
    name=net.attrib['name'].removeprefix('/')
    for node in net.findall('node'):
        if not node.attrib['ref'].startswith('#') and not name.startswith('unconnected-'):
            sch[node.attrib['ref'],node.attrib['pin']]=name
assert expected==sch,{'missing':list(set(expected.items())-set(sch.items())),'extra':list(set(sch.items())-set(expected.items()))}
erc=json.loads((root/'exports/erc.json').read_text(encoding='utf8'))
drc=json.loads((root/'exports/current-drc.json').read_text(encoding='utf8'))
assert not [v for sheet in erc['sheets'] for v in sheet['violations']]
assert not drc['violations'] and not drc['unconnected_items']
parts={x['ref']:x for x in d['parts']}
for f in b.GetFootprints():
    x=parts[f.GetReference()]
    assert f.IsDNP()==x['dnp'] and f.GetValue()==x['value']
    assert abs(p.ToMM(f.GetPosition().x)-x['x'])<.00001
    assert abs(p.ToMM(f.GetPosition().y)-x['y'])<.00001
    if x['kind']!='mechanical' and not f.GetReference().startswith('TP'):
        tech=p.FP_THROUGH_HOLE if any(pd.GetAttribute()==p.PAD_ATTRIB_PTH for pd in f.Pads())else p.FP_SMD
        assert f.GetAttributes()&tech,'Physical-pad/native-assembly mismatch: '+f.GetReference()
def pins(ref,numbers):return [actual[ref,str(n)] for n in numbers]
assert pins('J1',[4,2])==['VIN_DC','GND'] and ('J1','3')not in actual
assert pins('F1',[1,2])==['VIN_DC','VIN_FUSED']
assert pins('Q6',[1,2,3])==['REVERSE_GATE','VIN_PROTECTED','VIN_FUSED']
assert pins('U10',[3,6,2,7,5])==['VIN_PROTECTED','UPS_BACKUP_5V','POWER_REG_5V','POWER_REG_5V','UPS_CTL_VCC']
assert pins('JP4',[1,2,3])==['VIN_PROTECTED','POWER_BUS','POWER_REG_5V']
assert pins('J2',[1,2])==['BAT_SENSE_IN','GND']
assert pins('J4',[1,2])==['NTC_PACK','GND']
assert pins('U8',[4,5,8,9])==['VIN_PROTECTED','BAT_SENSE_IN','UPS_CHG_CE','GND']
assert pins('J18',[1,2,3,4])==['GND','DEBUG_ESP_TX43','DEBUG_ESP_RX44','TTL_5V']
assert actual['J13','28']=='CHG_DISABLE_IO38' and ('J13','29')not in actual
assert all(not parts[r]['dnp']for r in ['R26','R27','R30'])
assert all(parts[r]['dnp']for r in ['R28','R29','R31','J22'])
assert actual['J19','2']=='MODEM_3V8' and actual['J20','1']=='EXT_MODEM_3V8'
assert d['input_power']['range_at_connector_v']==[4.5,5.5]
assert d['input_power']['input_path_design_current_A']==2
assert not any(t.GetLayer()==p.In1_Cu for t in b.GetTracks() if not isinstance(t,p.PCB_VIA))
ids=json.loads((root/'schematic-ids.json').read_text(encoding='utf8'))
for f in b.GetFootprints():
    if f.GetReference()in ids['symbols']:
        path=p.KIID_PATH();path.push_back(p.KIID(ids['root']));path.push_back(p.KIID(ids['symbols'][f.GetReference()]));f.SetPath(path)
p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
# Stable text bytes across Windows KiCad and Git checkouts are required by
# the source-PCB and package SHA256 contract.
saved=root/'voice_mainboard_v3.kicad_pcb'
saved.write_bytes(saved.read_bytes().replace(b'\r\n',b'\n'))
vias=[t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)]
report={
 'revision':d['revision'],'electrical_parts':len(sch and [x for x in d['parts']if x['kind']!='mechanical']),
 'footprints':len(list(b.GetFootprints())),'connected_unique_pin_net_mappings':len(expected),
 'xml_netlist_equals_pcb':True,'erc_violations':0,'drc_violations':0,'unconnected_links':0,
 'assembly_values_dnp_placement_checked':True,'input_and_ups_pin_contract_checked':True,
 'native_assembly_flags_match_physical_pad_technology':True,
 'reference_layer':'In1.Cu; no signal traces','through_via_drills_mm':dict(collections.Counter(str(round(p.ToMM(v.GetDrill()),3))for v in vias)),
 'board_size_mm':d['dimensions_mm'],'layers':b.GetCopperLayerCount(),
 'routing_complete':True,'integrated_ups':True,'official_protocol_modified':False,'firmware_modified':False,
 'manufacturing_ready':False,
 'open_qualifications':['Power-converter closed-loop / startup / load / switch / thermal tests',
 'ML307 module and SIM/socket physical land signoff',
 'Exact power shunt/contact resistance and stock for all MPNs',
 'Actual enclosure, harness, antenna and USB validation'],
}
(root/'exports/validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,ensure_ascii=True))
