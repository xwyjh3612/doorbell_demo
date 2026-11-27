"""Read-only schematic/PCB audit and reproducible, explicitly scoped SPICE runs.

The dynamic test is a passive hold-up sensitivity model. It does not substitute
for the actual converter/mux semiconductor models or an assembled-board test.
"""
from pathlib import Path
import hashlib, itertools, json, math, re, sys, os
import xml.etree.ElementTree as ET
import pcbnew as p

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT.parent / 'voice_mainboard_v2'))
from spice_runtime import run
FILE = Path(os.environ.get('A18_AUDIT_BOARD',str(ROOT/'voice_mainboard_v8_a18.kicad_pcb'))).resolve()
ROOT = FILE.parent
OUT = ROOT / 'exports/electrical-audit'
OUT.mkdir(parents=True, exist_ok=True)
b = p.LoadBoard(str(FILE))
fps = {f.GetReference(): f for f in b.GetFootprints()}
design = json.loads((ROOT / 'design.json').read_text(encoding='utf-8'))
parts = {q['ref']: q for q in design['parts']}

def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()

def resistance(ref):
    match = re.match(r'([0-9.]+)([kM]?)', fps[ref].GetValue())
    assert match, ref
    return float(match[1]) * {'': 1, 'k': 1000, 'M': 1000000}[match[2]]

def pins(ref):
    return {d.GetNumber(): d.GetNetname() for d in fps[ref].Pads() if d.GetNumber()}

def xy(item):
    return [p.ToMM(item.GetPosition().x), p.ToMM(item.GetPosition().y)]

assert len(parts) == len(fps) == len(list(b.GetFootprints()))
assert b.GetCopperLayerCount() == design['layers']
for ref, q in parts.items():
    f = fps[ref]
    assert f.GetValue() == q['value'], (ref, f.GetValue(), q['value'])
    assert f.IsDNP() == q['dnp'], ref
    assert f.GetLayer() == (p.F_Cu if q['side'] == 'F' else p.B_Cu), ref
    assert math.dist(xy(f), [q['x'], q['y']]) < .001, ref
    for d in f.Pads():
        expected = q['pins'].get(d.GetNumber(), '')
        assert d.GetNetname() == expected or (not expected and d.GetNetname().startswith('unconnected-')), (ref, d.GetNumber())

native = {(ref, d.GetNumber()): d.GetNetname() for ref, f in fps.items()
          for d in f.Pads() if d.GetNumber() and d.GetNetname()
          and not d.GetNetname().startswith('unconnected-')}
xml = {}
for n in ET.parse(ROOT / 'exports/netlist.xml').getroot().findall('./nets/net'):
    if n.attrib['name'].startswith('unconnected-'):
        continue
    for node in n.findall('node'):
        if not node.attrib['ref'].startswith('#'):
            xml[(node.attrib['ref'], node.attrib['pin'])] = n.attrib['name'].removeprefix('/')
assert native == xml, {'PCB_only': list(native.items() - xml.items()), 'schematic_only': list(xml.items() - native.items())}
contracts = {
    'DC_center_positive': pins('J1')['4'] == 'VIN_DC' and pins('J1')['2'] == 'GND',
    'cell_negative_separate_from_system_ground': pins('J23')['2'] == 'CELL_NEG' and pins('U17')['2'] == 'CELL_NEG' and pins('U17')['4'] == 'GND',
    'speaker_bridge_not_grounded': pins('U14')['9'] == 'SPK_PLUS' and pins('U14')['10'] == 'SPK_MINUS',
    'UART_direction_and_level_domains': pins('U3')['3'] == 'ESP_TX17' and pins('U3')['4'] == 'M_RX_1V8'
        and pins('U3')['5'] == 'ESP_3V3' and pins('U4')['3'] == 'ESP_RX18'
        and pins('U4')['4'] == 'M_TX_1V8' and pins('U4')['5'] == 'GND',
    'native_ESP_USB_pin_assignment': pins('U7')['13'] == 'ESP_USB_DM19' and pins('U7')['14'] == 'ESP_USB_DP20',
    'optional_radar_pin_assignment': pins('U7')['6'] == 'RADAR_RX6' and pins('U7')['12'] == 'RADAR_TX8',
    'PSRAM_reserved_GPIO_not_connected': all(not parts['U7']['pins'][n] for n in ['28', '29', '30']),
    'power_source_status_is_3V3_pullup': pins('R72') == {'1': 'ESP_3V3', '2': 'SUPPLY_BAT_N47'},
    'charge_pause_GPIO38_to_CE': pins('Q7') == {'1': 'CHG_DISABLE_IO38', '2': 'GND', '3': 'CHG_CE'},
    'battery_ADC_GPIO2': pins('U7')['38'] == 'BAT_ADC2',
    'LED_supply_above_vendor_3p3V_minimum': pins('D2')['4'] == 'MODEM_3V8' and pins('C74')['1'] == 'MODEM_3V8',
    'modem_hardware_reset_GPIO21_open_drain': pins('U7')['23'] == 'RESET_CTL'
        and pins('Q2') == {'1':'RESET_CTL','2':'GND','3':'MODEM_RESET_N'}
        and pins('U1')['15'] == 'MODEM_RESET_N'
        and set(pins('R8').values()) == {'RESET_CTL','GND'}
        and pins('C19') == {'1':'MODEM_RESET_N','2':'GND'},
}
assert all(contracts.values()), contracts

def corners(vref, top, bottom, rtol):
    values = [v * (1 + resistance(top)*(1+rtol*a)/(resistance(bottom)*(1+rtol*z)))
              for v, a, z in itertools.product(vref, [-1, 1], [-1, 1])]
    return {'nominal_V': sum(vref)/2 * (1+resistance(top)/resistance(bottom)),
            'min_V': min(values), 'max_V': max(values), 'reference_min_max_V': vref,
            'resistor_tolerance': rtol, 'scope': 'unloaded feedback arithmetic, not dynamic regulation'}

rails = {
    'MODEM_3V8': corners([.591, .609], 'R2', 'R3', .001),
    'ESP_3V3': corners([.591, .609], 'R59', 'R60', .01),
    'BAT_BOOST_5V': corners([.588, .612], 'R61', 'R62', .001),
}
assert 3.4 < rails['MODEM_3V8']['min_V'] < rails['MODEM_3V8']['max_V'] < 4.5
assert 3.0 < rails['ESP_3V3']['min_V'] < rails['ESP_3V3']['max_V'] < 3.6
assert rails['BAT_BOOST_5V']['max_V'] < 5.5

# Explicit interruption of BOTH ideal sources stresses the actual passive
# capacitance assumption. Delays are swept, not represented as a vendor spec.
traces = []
hold_up = []
for capacitance_scale, delay_us in itertools.product([.25, .5, 1.0], [5, 20, 50, 100]):
    cap = (22+22+22)*1e-6*capacitance_scale  # C4,C5,C72; effective value not qualified
    t_off = .001
    t_on = t_off + delay_us*1e-6
    lines = [
        'Vsource source 0 4.5',
        f'Vcontrol control 0 PWL(0 3.3 {t_off-.0000001} 3.3 {t_off} 0 {t_on} 0 {t_on+.0000001} 3.3 .003 3.3)',
        'Ssource source feed control 0 IDEAL_MUX',
        '.model IDEAL_MUX SW(Ron=.05 Roff=1e12 Vt=1.65 Vh=0)',
        'Rpath feed sys .05',
        'Resr sys cap .02', f'Csys cap 0 {cap:.12g}',
        # C8 is on SYS_5V, not on the external side of the mux. Include it.
        'Rbulk sys bulk .12', 'Cbulk bulk 0 376u',
        'Bload sys 0 I=2*min(max(v(sys)/3,0),1)', 'Rleak sys 0 1G',
        '.options reltol=.001 abstol=1n vntol=1u', '.tran 100n .003',
    ]
    label = f'hold_up_cap{int(capacitance_scale*100)}_delay{delay_us}us'
    v, _ = run(label, lines, ['v(sys)', 'v(cap)', 'i(vsource)'], OUT)
    assert abs(v['i(vsource)'][0]+2) < .001, 'load current was not applied'
    assert abs(v['v(sys)'][0]-4.3) < .001, 'source path drop mismatch'
    window = [i for i, t in enumerate(v['time']) if t_off <= t <= t_on+1e-7]
    minimum = min(v['v(sys)'][i] for i in window)
    hold_up.append({'capacitance_scale': capacitance_scale, 'effective_C_uF': cap*1e6,
                    'C8_assumed_min_uF': 376, 'C8_path_and_ESR_assumed_ohm': .12,
                    'assumed_break_us': delay_us, 'load_A': 2, 'input_V': 4.5,
                    'min_system_V': minimum, 'stays_above_assumed_4p1V_input_floor': minimum >= 4.1,
                    'ngspice_completed': True})
    if delay_us in [5, 100] and capacitance_scale == .5:
        stride = max(1, len(v['time'])//1600)
        traces.append({'case': label, 'time_ms': [t*1000 for t in v['time'][::stride]], 'SYS_V': v['v(sys)'][::stride]})

peak_budget = []
for cell_V, efficiency, load_A in itertools.product([3.0, 3.3, 4.2], [.8, .9], [.2, .5, 2.0]):
    avg = 5*load_A/(cell_V*efficiency)
    # Worst switching-frequency and 20% inductance tolerance from BOM.
    ripple = cell_V*(1-cell_V/5)/(2.2e-6*.8*.7e6)
    peak_budget.append({'cell_V': cell_V, 'assumed_efficiency': efficiency, 'system_load_A': load_A,
                        'cell_average_A': avg, 'calculated_inductor_peak_A': avg+ripple/2,
                        'guaranteed_30k_ISET_minimum_available': False})

adc_scale = resistance('R18')/(resistance('R17')+resistance('R18'))
report = {
    'product': '语音对讲主板 A18 V8', 'PCB_sha256': sha(FILE),
    'schematic_sha256': sha(FILE.with_suffix('.kicad_sch')),
    'netlist_sha256': sha(ROOT/'exports/netlist.xml'),
    'part_count_including_DNP_and_testpoints': len(fps), 'connected_pins_checked': len(native),
    'PCB_matches_schematic_netlist': True, 'pin_contracts': contracts,
    'voltage_corners': rails, 'battery_ADC_scale': adc_scale,
    'board_thickness_mm': p.ToMM(b.GetDesignSettings().GetBoardThickness()),
    'LED_supply_VDD_min_max_V': [rails['MODEM_3V8']['min_V'],rails['MODEM_3V8']['max_V']],
    'LED_logic_high_margin_V': .8*rails['ESP_3V3']['min_V']-.55*rails['MODEM_3V8']['max_V'],
    'battery_ADC_at_4p242V_V': 4.242*adc_scale,
    'nominal_charge_current_mA': 1200/resistance('R64')*1000,
    'external_only_topology': 'VIN_PROTECTED -> TPS2117 VIN1 -> SYS_5V; battery not in series',
    'passive_hold_up_simulation': hold_up,
    'hold_up_model_scope': 'Actual ngspice passive ESR/capacitor with ideal switched source. Assumed total effective capacitance and delays; NOT TPS2117/converter model, NOT a pass/fail qualification of actual UPS.',
    'battery_peak_budget': peak_budget,
    'manufacturer_sources': {
        'SY8089': 'build/v4-low-cost-candidates/SY8089A1AAC.txt; FB 591/600/609mV',
        'ETA1096': 'build/ups-bom-20261124/ETA1096-C7435200.txt; FB .588/.600/.612V; 30k current limit only typical',
        'TP4056': 'build/ups-bom-20261124/TP4056-MS-C7473158.txt',
    },
    'unresolved': [
        'No actual SY8089/ETA1096/TPS2117 dynamic manufacturer macromodel used.',
        'Effective MLCC capacitance under DC bias not yet qualified.',
        'Cell capacity, high-rate discharge, NTC specification and enclosure fit not frozen.',
        '2A battery-mode peak support and thermal behavior need assembled-board measurement.',
        'GPIO38 charge pause is routed; 80/70 SOC policy not implemented in firmware.',
        'TEMP short to ground can disable TP4056 temperature monitoring; open NTC suspension is not short-circuit protection.',
    ],
    'full_board_simulated': False, 'actual_2A_qualified': False, 'manufacturing_ready': False,
}
(OUT/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(OUT/'sampled-traces.json').write_text(json.dumps(traces, separators=(',', ':')), encoding='utf-8')
print(json.dumps({'connected_pins_checked': len(native), 'contracts_passed': contracts,
                  'voltage_corners': rails, 'ngspice_cases': len(hold_up),
                  'full_board_simulated': False}, ensure_ascii=False, indent=2))
