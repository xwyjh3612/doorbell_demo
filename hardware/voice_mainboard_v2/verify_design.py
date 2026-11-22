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
route=d['usb_transport_reserve']
part_map={p['ref']:p for p in d['parts']}
for fp in b.GetFootprints():
    assert fp.IsDNP()==part_map[fp.GetReference()]['dnp'],'PCB population flags differ from assembly contract'
assert all(not part_map[r]['dnp'] for r in route['service_links'])
assert all(part_map[r]['dnp'] for r in route['host_links'])
assert ('J13','28')not in actual and ('J13','29')not in actual
assert [actual[('J22',str(n))]for n in [1,2,3]]==['GND','ESP_USB_DP20','ESP_USB_DM19']
assert part_map['J22']['dnp'],'Default AT assembly must leave USB Host header unpopulated'
assert [actual[('J19',str(n))] for n in [1,2,3]]==['BUCK_3V8','MODEM_3V8','EXT_MODEM_3V8']
assert [actual[('J20',str(n))] for n in [1,2]]==['EXT_MODEM_3V8','GND']
assert actual[('L1','2')]=='BUCK_3V8' and actual[('R2','1')]=='BUCK_3V8'
power=d['input_power']
assert power['range_at_connector_v']==[4.5,5.5] and power['input_path_design_current_A']==2
assert actual[('J1','1')]==actual[('R19','1')]==actual[('F1','1')]=='VIN_DC'
assert actual[('F1','2')]==actual[('Q6','3')]=='VIN_FUSED'
assert actual[('Q6','2')]==actual[('J2','1')]==actual[('JP4','1')]=='VIN_PROTECTED'
assert actual[('JP4','2')]==actual[('U2','3')]==actual[('U6','2')]=='POWER_BUS'
assert actual[('JP4','3')]==actual[('J3','1')]=='POWER_REG_5V'
assert actual[('U6','9')]==actual[('JP1','1')]=='BOARD_REG_5V'
assert [actual[('JP1',str(n))] for n in [1,2,3]]==power['selector_pin_nets']
assert actual[('J3','1')]=='POWER_REG_5V' and actual[('J21','1')]=='BENCH_REG_5V'
assert not any('VIN_DC' in p['pins'].values() and 'SYS_5V' in p['pins'].values() for p in d['parts']), 'Raw input bypass must not exist'
ids=json.loads((ROOT/'schematic-ids.json').read_text(encoding='utf-8'))
for f in b.GetFootprints():
    if f.GetReference() in ids['symbols']:
        path=pcb.KIID_PATH();path.push_back(pcb.KIID(ids['root']));path.push_back(pcb.KIID(ids['symbols'][f.GetReference()]));f.SetPath(path)
pcb.SaveBoard(str(ROOT/(PROJECT+'.kicad_pcb')),b)
report={'revision':d['revision'],'kicad_version':pcb.Version(),'electrical_parts':len([p for p in d['parts'] if p['kind']!='mechanical']),
 'ml307_pad_count':109,'connected_unique_pin_net_mappings':len(expected),'netlist_matches_pcb':True,'schematic_erc_violations':len(ev),
 'placement_drc_violations':len(drc['violations']),'unrouted_links':len(drc['unconnected_items']),
 'manufacturing_ready':False,'rf_routed':False,'usb_routed':False,'ups_chip_frozen':False,'supplier_ml307_footprint_signoff':False,
 'usb_host_reserved':True,'usb_route_population_checked':True,'usb_host_hardware_tested':False,
 'modem_power_selector_reserved':True,'modem_power_selector_hardware_tested':False,
 'input_range_v':power['range_at_connector_v'],'input_path_design_current_A':2,
 'raw_input_bypass_absent':True,'regulated_power_selector_checked':True,'wide_input_operation_verified':False,
 'mechanical_fit_verified':False,'full_power_simulation':False,'physical_electrical_tests':False,'firmware_modified':False}
tracks=list(b.GetTracks())
reference_layer_clear=not any(t.GetLayer()==pcb.In1_Cu and not isinstance(t,pcb.PCB_VIA)for t in tracks)
assert reference_layer_clear,'Signal trace splits the reserved In1 ground reference'
report.update(copper_items=len(tracks),partially_routed=bool(tracks)and bool(drc['unconnected_items']),
              copper_connected=bool(tracks)and not drc['unconnected_items'],
              continuous_reference_layer='In1.Cu',reference_layer_free_of_signal_traces=reference_layer_clear,
              minimum_copper_clearance_mm=.2,minimum_track_width_mm=.2,
              minimum_via_diameter_mm=.45,minimum_through_drill_mm=.2,
              minimum_via_annular_ring_mm=.125,
              rf_tracks_present=any(t.GetNetname()in['RF_ANT','RF_FEED']for t in tracks),
              rf_impedance_verified=False,usb_impedance_verified=False,assembly_population_flags_checked=True)
report.update(rf_routed=report['copper_connected']and report['rf_tracks_present'],
              usb_routed=report['copper_connected']and all(any(t.GetNetname()==name for t in tracks)for name in ['M_USB_DP','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19','SERVICE_USB_DP','SERVICE_USB_DM']),
              usb_host_connector='J22: GND / DP20 / DM19',usb_host_pair_layer='F.Cu')
if report['copper_connected']:
    d['status']='CONNECTED ENGINEERING REVIEW - POWER/RF/USB AND MANUFACTURING REVIEW REQUIRED'
    d['usb_transport_reserve']['routed']=report['usb_routed']
    d['usb_transport_reserve']['host_connector']='J22 GND/DP20/DM19; J13 pins28/29 NC'
    (ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(ROOT/'exports/validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
