"""Revise the V4 native board for a user-assumed regulated 5V UPS boundary.

The six solder terminals are an electrical interface, not a guessed PMIC land
pattern. Regeneration restores a partially routed starting board from V4.
"""
from pathlib import Path
import copy, hashlib, importlib.util, json, shutil
import pcbnew as p

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'voice_mainboard_v4'
PROJECT = 'voice_mainboard_v5'
LOCAL = ROOT / 'VoiceV2.pretty'
for directory in [LOCAL, ROOT / 'exports', ROOT / 'cost', ROOT / 'sources']:
    directory.mkdir(parents=True, exist_ok=True)
for file in (BASE / 'VoiceV2.pretty').glob('*.kicad_mod'):
    shutil.copy2(file, LOCAL / file.name)
shutil.copy2(BASE / 'sources/ml307c-dl-library.json', ROOT / 'sources/ml307c-dl-library.json')
shutil.copy2(BASE / '.gitattributes', ROOT / '.gitattributes')
with (ROOT / '.gitattributes').open('a',encoding='utf8',newline='\n') as attrs:
    attrs.write('*.zip -text -diff -merge\n')
(ROOT / '.gitignore').write_text('*.kicad_prl\n*.lck\n*-backups/\n__pycache__/\n', encoding='utf8')

spec = importlib.util.spec_from_file_location('v2helper', BASE.parent / 'voice_mainboard_v2/generate_design.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
g.ROOT = ROOT
g.LOCAL = LOCAL
g.PROJECT = PROJECT
g.board = board = p.LoadBoard(str(BASE / 'voice_mainboard_v4.kicad_pcb'))
assert board.GetCopperLayerCount() == 2
data = copy.deepcopy(json.loads((BASE / 'design.json').read_text(encoding='utf8')))
prices = json.loads((BASE / 'cost/part-price-inputs.json').read_text(encoding='utf8'))
research = json.loads((BASE / 'cost/低价替代料核查.json').read_text(encoding='utf8'))
candidate = {q['role']: q for q in research['candidates']}
parts = {q['ref']: q for q in data['parts']}
fps = {f.GetReference(): f for f in board.GetFootprints()}
g.nets = {n.GetNetname(): n for n in board.GetNetsByNetcode().values() if n.GetNetname()}
g.parts = []

removed = {ref for ref, q in parts.items() if q['group'].startswith('02 ')}
removed |= {'U9', 'L3', 'C41', 'C42', 'C43', 'C45', 'R40', 'R41', 'D2', 'D3', 'D4', 'TP11'}
held_removed = []
for ref in removed:
    fp = fps.pop(ref)
    held_removed.append(fp)
    board.Remove(fp)
    parts.pop(ref)
    prices.pop(ref, None)

# Release inherited routing so the new wide trunks can be placed first.
for track in list(board.GetTracks()):
    held_removed.append(track)
    board.Remove(track)
for zone in list(board.Zones()):
    if not zone.GetIsRuleArea():
        held_removed.append(zone)
        board.Remove(zone)


def assign(ref, pins):
    q = parts[ref]
    q['pins'] = pins
    for pad in fps[ref].Pads():
        name = pins.get(pad.GetNumber(), '')
        if name:
            pad.SetNet(g.net(name))
        else:
            pad.SetNetCode(0)


def move(ref, x, y, angle=None):
    fp = fps[ref]
    fp.SetPosition(g.v(x, y))
    if angle is not None:
        fp.SetOrientationDegrees(angle)
    parts[ref].update(x=x, y=y, angle=fp.GetOrientationDegrees())


def value(ref, text):
    parts[ref].update(value=text, mpn=text)
    fps[ref].SetValue(text)


def add(ref, text, footprint, x, y, pins, group, names=None, price=0, basis='unquoted passive allowance'):
    fp = g.add(ref, text, footprint, x, y, pins, group, names=names)
    fp.SetAttributes(p.FP_THROUGH_HOLE if any(pd.GetAttribute() == p.PAD_ATTRIB_PTH for pd in fp.Pads()) else p.FP_SMD)
    q = g.parts.pop()
    q.update(mpn=text, lcsc=None, side='F', price_basis=basis)
    parts[ref] = q
    fps[ref] = fp
    prices[ref] = {'unit_cny': price, 'basis': basis, 'source': ''}
    return fp


for ref, q in parts.items():
    assign(ref, {number: 'MODEM_3V8' if net in ['POWER_BUS', 'ADAPTER_3V8'] else net for number, net in q['pins'].items()})

# Replace the primary buck and move its switching loop beside modem VBAT.
old_fp = fps['U2']
held_removed.append(old_fp)
board.Remove(old_fp)
fp = p.FOOTPRINT(None)
fp.SetFPID(p.LIB_ID('VoiceV2','TI_DDC0006A'))
for number,x,y in [(1,-1.35,-.95),(2,-1.35,0),(3,-1.35,.95),(4,1.35,.95),(5,1.35,0),(6,1.35,-.95)]:
    pad=p.PAD(fp)
    pad.SetNumber(str(number))
    pad.SetAttribute(p.PAD_ATTRIB_SMD)
    pad.SetShape(p.PAD_SHAPE_ROUNDRECT)
    pad.SetSize(g.v(1.1,.6))
    pad.SetRoundRectRadiusRatio(.05/.6)
    layers=p.LSET()
    for layer in [p.F_Cu,p.F_Mask,p.F_Paste]:layers.AddLayer(layer)
    pad.SetLayerSet(layers)
    pad.SetPosition(g.v(x,y))
    fp.Add(pad)
for layer,x1,y1,x2,y2 in [(p.F_Fab,-.875,-1.525,.875,1.525),(p.F_CrtYd,-2.15,-1.8,2.15,1.8)]:
    pts=[(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
    for a,z in zip(pts,pts[1:]+pts[:1]):g.line(fp,a,z,layer,.05 if layer==p.F_CrtYd else .1)
fp.SetLibDescription('TI DDC0006A recommended land example4214841/A08-2016: pads1.1x0.6mm, columns2.7mm apart, pitch0.95mm; transcribed from TPS563201 datasheet page25.')
fp.SetAttributes(p.FP_SMD)
fp.Reference().SetVisible(False)
p.FootprintSave(str(LOCAL),fp)
(ROOT/'sources/tps563201-land.json').write_text(json.dumps({'model':'TPS563201DDCR','package':'DDC0006A',
    'source_url':'https://www.ti.com/lit/ds/symlink/tps563201.pdf','archived_drawing':'4214841/A08-2016 page25',
    'pad_size_mm':[1.1,.6],'column_center_spacing_mm':2.7,'pitch_mm':.95,'round_radius_mm':.05,
    'assembler_qualified':False},indent=2)+'\n',encoding='utf8')
fp.SetReference('U2')
fp.SetValue('TPS563201DDCR')
fp.SetAttributes(p.FP_SMD)
fp.SetPosition(g.v(50, 11))
fp.Value().SetVisible(False)
board.Add(fp)
fps['U2'] = fp
parts['U2'].update(value='TPS563201DDCR', mpn='TPS563201DDCR', lcsc=None,
    footprint='VoiceV2:TI_DDC0006A', x=50, y=11, angle=0,
    names={'1':['GND','power_in'], '2':['SW','passive'], '3':['VIN','power_in'],
           '4':['VFB','input'], '5':['EN','input'], '6':['VBST','passive']},
    source='https://www.ti.com/lit/ds/symlink/tps563201.pdf',
    note='TI DDC pin map: GND1 SW2 VIN3 VFB4 EN5 VBST6. UPS regulated5V assumption; no PG. 39.2k/10k gives3.77856V.')
assign('U2', {'1':'GND', '2':'BUCK_SW', '3':'SYS_5V', '4':'BUCK_FB', '5':'BUCK_EN', '6':'BUCK_BST'})
for ref in ['U13', 'C59']:
    assign(ref, {n: 'SYS_5V' if net == 'MODEM_3V8' else net for n, net in parts[ref]['pins'].items()})
assign('R1', {'1':'SYS_5V', '2':'BUCK_EN'})
for ref in ['C4', 'C5']:
    assign(ref, {'1':'SYS_5V', '2':'GND'})
value('R2', '39.2k 0.1% MODEM 3.77856V')
for ref, xy in {
    'L1':(48,4.2,90), 'C3':(53.75,8.25,0), 'C4':(49,15,90), 'C5':(66,65,90),
    'C6':(54,2.8,0), 'C7':(54,5.8,0), 'R1':(54.5,17.5,0),
    'R2':(54,11.5,0), 'R3':(54,14.5,0), 'C37':(54.5,22,0),
    'C8':(63,7,0), 'C10':(61.5,15.2,0), 'C11':(65,15,0), 'C12':(69,15,0),
    'R57':(7,15.8,0), 'C56':(8,13.5,0), 'C57':(7,11,0), 'C58':(7,8,0), 'R60':(25,32,180), 'R28':(81.1,33.5,0),
    'R10':(55,34.5,180), 'R11':(55,31.5,180), 'TP1':(72,9,0), 'TP6':(72,12,0),
}.items():
    move(ref, *xy)
# Keep the 470u reservoir on the 5V upstream rail. Output uses 2x22u+10u.
assign('C8', {'1':'SYS_5V', '2':'GND'})
parts['C5']['dnp'] = True
fps['C5'].SetDNP(True)
parts['C5']['note'] = 'Optional extra UPS output capacitance, default DNP; C4 local22u + C8 upstream470u installed.'
parts['C8']['note'] = '470uF moved upstream to5V to avoid imposing ~500uF on the new buck loop. Modem output nominal2x22u+10u; DC bias/current step require qualification.'

# SY8089 shares the original SOT23-5 pin map. Add recommended feed-forward.
value('U13', 'SY8089A1AAC')
parts['U13']['source'] = candidate['esp_buck']['supplier_datasheet_url']
parts['U13']['note'] = 'Silergy EN1/GND2/LX3/IN4/FB5. RH100k/RL22.1k/Cff22p per3.3V application table; target3.31493V. Current production revision and hardware validation pending.'
value('R59', '100k 1% RH ESP')
value('R60', '22.1k 1% RL ESP')
add('C63', '22p ESP CFF', 'Capacitor_SMD:C_0603_1608Metric', 31.5, 33,
    {'1':'ESP_3V3', '2':'ESP_FB'}, '06 ESP 3.3V / AUDIO 5V / AMPLIFIER', price=.05)

# SIM ESD array, four protected contacts, referenced to SIM's switched supply.
held_removed.append(fps['D1'])
board.Remove(fps['D1'])
fp = g.io.FootprintLoad(str(g.LIB / 'Package_TO_SOT_SMD.pretty'), 'SOT-23-6', False)
fp.SetReference('D1')
fp.SetValue('SRV05-4 MSKSEMI')
fp.SetPosition(g.v(72, 47))
fp.SetAttributes(p.FP_SMD)
fp.Value().SetVisible(False)
board.Add(fp)
fps['D1'] = fp
parts['D1'].update(value='SRV05-4 MSKSEMI', mpn='SRV05-4', lcsc=None,
    footprint='Package_TO_SOT_SMD:SOT-23-6', x=72, y=47, angle=0,
    names={str(i):[('GND' if i==2 else 'VCC' if i==5 else 'IO'), 'passive'] for i in range(1,7)},
    source=candidate['sim_esd_array']['supplier_datasheet_url'],
    note='IO1/3/4/6; GND2; VCC5=SIM_VCC. Fourth IO protects SIM_VCC itself; powered-off injection and actual clamps need qualification.')
assign('D1', {'1':'SIM_DATA', '2':'GND', '3':'SIM_CLK', '4':'SIM_RESET', '5':'SIM_VCC', '6':'SIM_VCC'})
parts['J10']['note'] = 'Existing JAE SF72S006 footprint retained pending exact pad/mechanical drawing for SHOU HAN NANO SIM 7P-Ow H1.45. Do not substitute by connector pin count; current socket cost remains2.51.'
for role, ref in [('modem_buck_conditional','U2'), ('esp_buck','U13'), ('sim_esd_array','D1')]:
    q = candidate[role]
    prices[ref] = {'unit_cny':q['public_unit_cny'], 'basis':f"public candidate tier {q['selected_public_tier_quantity']} for1000pcs; not factory quote", 'source':q['source']}

# A real editable electrical interface with generous through solder terminals.
# Its outline reserves PCB area only; actual PMIC/inductor footprints remain TBD.
contract = p.FOOTPRINT(None)
contract.SetFPID(p.LIB_ID('VoiceV2', 'UPS_5V_CONTRACT_TBD'))
contract.SetAttributes(p.FP_THROUGH_HOLE)
locations = {'1':(-24,-6), '2':(-24,-2), '3':(24,-6), '4':(24,-2), '5':(-24,2), '6':(-24,6)}
for number, (x,y) in locations.items():
    pad = p.PAD(contract)
    pad.SetNumber(number)
    pad.SetAttribute(p.PAD_ATTRIB_PTH)
    pad.SetShape(p.PAD_SHAPE_CIRCLE)
    pad.SetSize(g.v(2.4,2.4))
    pad.SetDrillSize(g.v(1.2,1.2))
    layers = p.LSET.AllCuMask()
    layers.AddLayer(p.F_Mask)
    layers.AddLayer(p.B_Mask)
    pad.SetLayerSet(layers)
    pad.SetPosition(g.v(x,y))
    contract.Add(pad)
g.line(contract,(-20,-9),(20,-9),p.F_Fab,.1)
g.line(contract,(20,-9),(20,9),p.F_Fab,.1)
g.line(contract,(20,9),(-20,9),p.F_Fab,.1)
g.line(contract,(-20,9),(-20,-9),p.F_Fab,.1)
contract.SetLibDescription('Electrical contract only. Six solder terminals around a40x18mm reserved area, not an UPS module or charging IC footprint. Actual UPS design is pending.')
contract.Reference().SetVisible(False)
contract.Value().SetVisible(False)
p.FootprintSave(str(LOCAL),contract)
add('U15', 'UPS REGULATED 5V CONTRACT - IC TBD', 'VoiceV2:UPS_5V_CONTRACT_TBD', 34,64,
    {'1':'VIN_PROTECTED', '2':'GND', '3':'SYS_5V', '4':'GND', '5':'BAT_SENSE_IN', '6':'GND'},
    '02 UPS REGULATED 5V CONTRACT',
    names={'1':['ADAPTER_INPUT','power_in'], '2':['GND','power_in'], '3':['ASSUMED_REG5V_OUTPUT','power_out'],
           '4':['GND','power_in'], '5':['PROTECTED_1S_BATTERY','passive'], '6':['GND','power_in']},
    price=5, basis='user5CNY integrated power/UPS materials allowance; actual circuit unknown')
parts['U15'].update(kind='reserved_interface', note='Not a real PMIC symbol/footprint. Output5V is a user assumption. VIN/GND/5V/GND/BAT/GND terminals enable downstream board testing; no rawVIN-toSYS5V bypass. Battery terminal is for protected pack rail/ADC; charging/cutoff belong to future UPS circuit.')
# GPIO38 remains an uncommitted charger-control reserve.
assign('U7', {n: '' if net == 'CHG_DISABLE_IO38' else net for n, net in parts['U7']['pins'].items()})
data['gpio_contract']['charger_disable'] = None
data['gpio_contract']['charger_control_reserved_gpio'] = 38

# Replace obsolete test pads with explicit rails.
assign('TP7', {'1':'VIN_PROTECTED'})
assign('TP8', {'1':'MODEM_3V8'})
move('TP8',54.5,27)
move('TP9',57,54)
value('TP9', 'SYS_5V UPS OUTPUT TEST')

rule = p.ZONE(board)
rule.SetIsRuleArea(True)
rule.SetLayerSet(p.LSET.AllCuMask())
rule.SetDoNotAllowTracks(True)
rule.SetDoNotAllowVias(True)
rule.SetDoNotAllowCopperPour(True)
rule.SetDoNotAllowPads(True)
outline = rule.Outline()
outline.NewOutline()
for x,y in [(14,55),(54,55),(54,73),(14,73)]:
    outline.Append(p.FromMM(x),p.FromMM(y))
board.Add(rule)

for fp in fps.values():
    fp.Reference().SetLayer(p.F_Fab)
    fp.Reference().SetTextSize(g.v(.75,.75))
    fp.Reference().SetTextThickness(p.FromMM(.12))
    fp.Reference().SetVisible(False)
for q in parts.values():
    fps[q['ref']].SetDNP(q['dnp'])
    q['x'] = p.ToMM(fps[q['ref']].GetPosition().x)
    q['y'] = p.ToMM(fps[q['ref']].GetPosition().y)
    q['angle'] = fps[q['ref']].GetOrientationDegrees()

project = json.loads((BASE / 'voice_mainboard_v4.kicad_pro').read_text(encoding='utf8'))
project['meta']['filename'] = PROJECT + '.kicad_pro'
project['net_settings']['netclass_patterns'] = [
    {'netclass':'POWER','pattern':n} for n in ['VIN_DC','VIN_FUSED','VIN_PROTECTED','SYS_5V','MODEM_3V8','ESP_3V3']
] + [{'netclass':'RF','pattern':n} for n in ['RF_ANT','RF_FEED']]
(ROOT / (PROJECT + '.kicad_pro')).write_text(json.dumps(project,indent=2)+'\n', encoding='utf8')
(ROOT / (PROJECT + '.kicad_dru')).write_text('(version 1)\n', encoding='utf8')
p.SaveBoard(str(ROOT / (PROJECT + '.kicad_pcb')), board)
data.update(revision='V5-REGULATED-UPS5V-20261122', status='PARTIAL ROUTING / RESERVED UPS INTERFACE', parts=list(parts.values()),
    parent_PCB_sha256=hashlib.sha256((BASE/'voice_mainboard_v4.kicad_pcb').read_bytes()).hexdigest(),
    input_power={'nominal_v':5,'adapter_current_a':2,'connector_mm':[5.5,2.5], 'range_at_connector_v':[4.5,5.5],
        'UPS_output_assumed_v':5, 'UPS_output_validation_required_v':[4.75,5.25], 'modem_nominal_v':.768*(1+39.2/10),
        'ESP_nominal_v':.6*(1+100/22.1), 'full_power_or_transient_test_passed':False},
    power_architecture=['J1 -> F1/Q6 -> UPS input contract', 'protected1S battery -> future UPS contract; ESP ADC sense only',
        'assumed UPS regulated5V -> TPS563201 -> modem3.77856V',
        'assumed UPS regulated5V -> SY8089A1 -> ESP3.31493V + external microphone',
        'assumed UPS regulated5V -> I2S amplifier + optional radar'],
    ups_controls={'actual_chip_selected':False, 'full_UPS_qualified':False, 'output_is_user_assumption':True,
        'reserved_area_mm':[14,55,54,73], 'terminals':['VIN_PROTECTED','GND','SYS_5V','GND','BAT_SENSE_IN','GND']},
    assembly_open_items=['Actual UPS IC, full charging/cutoff/power-path circuit, footprint and current/thermal validation',
        'Cheap SIM socket exact mechanical/pad drawing; currently retain priced JAE socket',
        'C-DL full manufacturer hardware manual/AT firmware and actual assembly fit',
        'SY8089 current manufacturer specification, inductor ratings and ceramic DC bias',
        'Converter startup/transient/thermal and full-board power qualification',
        'RF/USB impedance and antenna test; current hardware USB mode unqualified',
        'Prototype long-call test, battery reporting and new power GPIO adaptation'],
    microphone='External INMP441 module, excluded from motherboard cost',
    user_price_assumptions={'ML307C-DL':10,'ESP32-S3-WROOM-1-N8R8':12,'5V_supply_and_UPS_materials':5},
    manufacturing_ready=False, firmware_modified=False)
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'cost/part-price-inputs.json').write_text(json.dumps(prices,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'sources/replacement-candidates.json').write_text(json.dumps(research,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('V5 created:',len(parts),'footprints; fresh routing required; UPS internal circuit remains TBD.')
for item in held_removed:
    item.thisown = False
