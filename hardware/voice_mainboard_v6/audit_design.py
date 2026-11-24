"""Independent saved PCB / schematic pin audit and resistor corner calculations."""
from pathlib import Path
import json,hashlib,collections,itertools,xml.etree.ElementTree as ET
import pcbnew as p
ROOT=Path(__file__).resolve().parent
FILE=ROOT/'voice_mainboard_v6.kicad_pcb';d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
parts={q['ref']:q for q in d['parts']};b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()}
assert len(fps)==len(list(b.GetFootprints()))==len(parts)
assert b.GetCopperLayerCount()==2
for ref,q in parts.items():
    f=fps[ref];assert f.GetValue()==q['value'] and f.IsDNP()==q['dnp'],ref
    assert f.GetLayer()==p.F_Cu,ref
    assert abs(p.ToMM(f.GetPosition().x)-q['x'])<.001 and abs(p.ToMM(f.GetPosition().y)-q['y'])<.001,ref
    for pd in f.Pads():
        expected=q['pins'].get(pd.GetNumber(),'')
        assert pd.GetNetname()==expected or (not expected and pd.GetNetname().startswith('unconnected-')),(ref,pd.GetNumber())
# Rework must preserve every existing non-UPS circuit, not only a unique count.
base=json.loads((ROOT.parent/'voice_mainboard_v5/design.json').read_text(encoding='utf8'))
rename={'L4':'L5','R61':'R75','R62':'R76','TP12':'TP15','TP13':'TP16','TP14':'TP17'}
preserved=0
for q in base['parts']:
    if q['ref'] in ['U15','U2','R1','C3']:continue
    target=parts[rename.get(q['ref'],q['ref'])]
    for n,net in q['pins'].items():
        if q['ref']=='U7' and n in ['24','25','34','39']:assert net=='';continue
        assert target['pins'][n]==net,(q['ref'],n)
    preserved+=1
assert parts['U17']['pins']=={'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NEG','4':'GND','5':'GND'}
assert parts['J23']['pins']=={'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NTC'}
assert parts['U18']['pins']['8']=='SUPPLY_BAT_N47'
assert parts['U7']['pins']['24']=='SUPPLY_BAT_N47'
assert parts['U7']['pins']['25']=='CHG_ACTIVE_N' and parts['U7']['pins']['39']=='CHG_FULL_N'
xml={};ncs={}
for net in ET.parse(ROOT/'exports/netlist.xml').getroot().findall('./nets/net'):
    for node in net.findall('node'):
        ref,n=node.attrib['ref'],node.attrib['pin']
        if net.attrib['name'].startswith('unconnected-'):
            assert not parts[ref]['pins'].get(n,'');ncs[(ref,n)]=net.attrib['name']
        elif not ref.startswith('#'):xml[(ref,n)]=net.attrib['name'].removeprefix('/')
native={(ref,pd.GetNumber()):pd.GetNetname() for ref,f in fps.items() for pd in f.Pads() if pd.GetNumber() and pd.GetNetname() and not pd.GetNetname().startswith('unconnected-')}
assert native==xml,{'missing_xml':list(native.items()-xml.items()),'missing_pcb':list(xml.items()-native.items())}
ids=json.loads((ROOT/'schematic-ids.json').read_text(encoding='utf8'))
for ref,f in fps.items():
    lib,name=parts[ref]['footprint'].split(':');f.SetFPID(p.LIB_ID(lib,name))
    for pd in f.Pads():
        nc=ncs.get((ref,pd.GetNumber()))
        if nc:
            net=b.FindNet(nc)
            if net is None:net=p.NETINFO_ITEM(b,nc);b.Add(net)
            pd.SetNet(net)
    if ref in ids['symbols']:
        path=p.KIID_PATH();path.push_back(p.KIID(ids['root']));path.push_back(p.KIID(ids['symbols'][ref]));f.SetPath(path)
    elif parts[ref]['kind']=='mechanical':f.SetAttributes(f.GetAttributes()|p.FP_BOARD_ONLY)
p.SaveBoard(str(FILE),b)
FILE.write_bytes(FILE.read_bytes().replace(b'\r\n',b'\n'))
def corners(ref,rt,rb,referr,rerr):
    vs=[ref*(1+a*referr)*(1+rt*(1+c*rerr)/(rb*(1+e*rerr))) for a,c,e in itertools.product([-1,1],repeat=3)]
    return {'nominal_v':ref*(1+rt/rb),'min_v':min(vs),'max_v':max(vs),'reference_error':referr,'resistor_error':rerr}
result={'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'unique_parts':len(parts),'layers':2,'all_components_front':True,
        'native_pin_contract_passed':True,'schematic_XML_matches_PCB_connected_pins':True,'connected_pins_checked':len(native),
        'baseline_circuits_checked':preserved,'voltage_corners':{
        'modem':corners(.6,100000,18700,.02,.001),'ESP':corners(.6,100000,22100,.02,.01),
        'boost':corners(.6,73200,10000,.02,.001),'mux_switch_input':corners(1,100000,33200,.08,.001)},
        'corner_scope':'Resistor arithmetic only; converter reference errors except TI mux are assumptions, not loaded voltage guarantees.',
        'battery_ADC_scale':2.5,'bare_cell_negative_is_GND':False,'full_motherboard_simulated':False,'2A_load_qualified':False,'manufacturing_ready':False}
(ROOT/'exports/design-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,indent=2))
