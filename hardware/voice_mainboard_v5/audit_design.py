"""Check native design contract, source geometry and simple voltage corners."""
from pathlib import Path
import hashlib,itertools,json,math,collections,xml.etree.ElementTree as ET
import pcbnew as p
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
parts={q['ref']:q for q in data['parts']}
file=ROOT/'voice_mainboard_v5.kicad_pcb'
b=p.LoadBoard(str(file))
fps={f.GetReference():f for f in b.GetFootprints()}
assert set(fps)==set(parts)
assert b.GetCopperLayerCount()==2
for ref,q in parts.items():
    fp=fps[ref]
    assert fp.GetValue()==q['value'],ref
    assert fp.IsDNP()==q['dnp'],ref
    assert fp.GetLayer()==p.F_Cu,ref
    for pad in fp.Pads():
        assert pad.GetNetname()==q['pins'].get(pad.GetNumber(),''),(ref,pad.GetNumber())
    assert abs(p.ToMM(fp.GetPosition().x)-q['x'])<.001 and abs(p.ToMM(fp.GetPosition().y)-q['y'])<.001,ref
assert set(parts['U2']['pins'].items())==set({'1':'GND','2':'BUCK_SW','3':'SYS_5V','4':'BUCK_FB','5':'BUCK_EN','6':'BUCK_BST'}.items())
assert [parts['U13']['pins'][str(i)] for i in range(1,6)]==['SYS_5V','GND','ESP_SW','SYS_5V','ESP_FB']
assert parts['C8']['pins']['1']=='SYS_5V'
assert parts['U1']['pins']['42']==parts['U1']['pins']['43']=='MODEM_3V8'
assert [parts['J18']['pins'][str(i)] for i in range(1,5)]==['GND','DEBUG_ESP_TX43','DEBUG_ESP_RX44','VIN_DC']
assert [parts['J16']['pins'][str(i)] for i in range(1,5)]==['RADAR_5V','GND','RADAR_RX6','RADAR_TX8']
assert parts['R58']['dnp']
assert all(parts[ref]['dnp'] for ref in ['R28','R29','R31'])
assert all(not parts[ref]['dnp'] for ref in ['R26','R27','R30'])
assert not any(pad.GetNetname() in ['POWER_BUS','BAT_ALLOWED','ADAPTER_3V8'] for fp in fps.values() for pad in fp.Pads())
netlist=ET.parse(ROOT/'exports/netlist.xml').getroot()
xml_pins={}
no_connect_pairs=[]
for net in netlist.findall('./nets/net'):
    for node in net.findall('node'):
        pair=(node.attrib['ref'],node.attrib['pin'])
        name=net.attrib['name']
        if name.startswith('unconnected-'):
            assert parts[pair[0]]['pins'].get(pair[1],'')=='',pair
            no_connect_pairs.append(pair)
        else:
            # KiCad prefixes local root-sheet labels with '/'; this design is flat.
            xml_pins[pair]=name.removeprefix('/')
native_pins={(ref,pad.GetNumber()):pad.GetNetname() for ref,fp in fps.items() for pad in fp.Pads() if pad.GetNumber() and pad.GetNetname()}
assert xml_pins==native_pins,{'missing_in_xml':list(set(native_pins.items())-set(xml_pins.items())),'missing_in_pcb':list(set(xml_pins.items())-set(native_pins.items()))}
tracks={t.m_Uuid.AsString():t for t in b.GetTracks()}
critical=json.loads((ROOT/'exports/critical-power-routes.json').read_text(encoding='utf8'))
retained=[]
for q in critical:
    if q['net'] in ['ESP_FB','ESP_3V3']:continue  # these branches were deliberately reworked
    ids=q.get('added_track_uuids',[])
    assert ids and all(uid in tracks for uid in ids),q
    retained.append({'net':q['net'],'from':['U15' if v=='U_UPS' else v for v in q['from']],
        'to':['U15' if v=='U_UPS' else v for v in q['to']],'copper_items_checked':len(ids),'width_mm':q['width_mm']})
power_widths={net:{str(w):n for w,n in collections.Counter(round(p.ToMM(t.GetWidth()),3)for t in b.GetTracks()if t.GetNetname()==net and not isinstance(t,p.PCB_VIA)).items()} for net in ['SYS_5V','MODEM_3V8','ESP_3V3']}
for pad in fps['U2'].Pads():
    number=int(pad.GetNumber())
    x=-1.35 if number<=3 else 1.35
    y={1:-.95,2:0,3:.95,4:.95,5:0,6:-.95}[number]
    center=fps['U2'].GetPosition()
    observed=(p.ToMM(pad.GetPosition().x-center.x),p.ToMM(pad.GetPosition().y-center.y),p.ToMM(pad.GetSize().x),p.ToMM(pad.GetSize().y))
    assert all(abs(a-z)<.001 for a,z in zip(observed,(x,y,1.1,.6)))
source=json.loads((ROOT/'sources/ml307c-dl-library.json').read_text(encoding='utf8'))
actual={pad.GetNumber():pad for pad in fps['U1'].Pads()}
assert len(actual)==109
for q in source['pads']:
    pad=actual[q['number']]
    center=fps['U1'].GetPosition()
    observed=[p.ToMM(pad.GetPosition().x-center.x),p.ToMM(pad.GetPosition().y-center.y),p.ToMM(pad.GetSize().x),p.ToMM(pad.GetSize().y)]
    expected=[q[k] for k in ['x_mm','y_mm','width_mm','height_mm']]
    assert all(abs(a-z)<.001 for a,z in zip(observed,expected)),q['number']
    assert parts['U1']['names'][q['number']][0]==source['pin_names'][q['number']]


def corners(reference,rt,rb,ref_tolerance,r_tolerance):
    values=[reference*(1+a*ref_tolerance)*(1+rt*(1+c*r_tolerance)/(rb*(1+d*r_tolerance))) for a,c,d in itertools.product([-1,1],repeat=3)]
    return {'nominal_v':reference*(1+rt/rb),'min_v':min(values),'max_v':max(values),
        'assumed_reference_tolerance':ref_tolerance,'assumed_resistor_tolerance':r_tolerance}


modem=corners(.768,39200,10000,.02,.001)
esp=corners(.6,100000,22100,.02,.01)
assert 3.4<modem['min_v']<modem['max_v']<4.5
assert 3<esp['min_v']<esp['max_v']<3.6
ids=json.loads((ROOT/'schematic-ids.json').read_text(encoding='utf8'))
for ref,fp in fps.items():
    if ref in ids['symbols']:
        path=p.KIID_PATH()
        path.push_back(p.KIID(ids['root']))
        path.push_back(p.KIID(ids['symbols'][ref]))
        fp.SetPath(path)
p.SaveBoard(str(file),b)
file.write_bytes(file.read_bytes().replace(b'\r\n',b'\n'))
report={'PCB_sha256':hashlib.sha256(file.read_bytes()).hexdigest(), 'native_pin_contract_passed':True,
    'schematic_XML_matches_PCB_connected_pins':True,'connected_pin_pairs_checked':len(native_pins),
    'schematic_explicit_no_connect_pairs_checked':len(no_connect_pairs),
    'preserved_primary_switch_and_power_connections':retained,'power_track_width_counts_mm':power_widths,
    'layers':2,'all_components_front':True,'modem_library_pads_checked':109,
    'TPS563201_DDC0006A_land_checked':True, 'official_firmware_changed':False,
    'voltage_resistor_corners':{'modem':modem,'ESP':esp},
    'corner_limits':'Independent resistor equations, assumed reference tolerances, no load/startup/temperature/ripple prediction',
    'battery_ADC_nominal_scale':2.5,'protected1S_4p2V_ADC_nominal_v':4.2/2.5,
    'UPS_5V_is_user_assumption':True,'UPS_internal_circuit_complete':False,
    'cheap_SIM_socket_footprint_complete':False,
    'full_motherboard_simulated':False,'manufacturing_ready':False}
(ROOT/'exports/design-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
