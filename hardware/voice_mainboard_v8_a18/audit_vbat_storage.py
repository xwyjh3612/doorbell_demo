"""Compare passive storage during an assumed modem regulator interruption."""
import hashlib
import json
import os
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE.parent/'voice_mainboard_v2'))
from spice_runtime import run

board = Path(os.environ['A18_AUDIT_BOARD']).resolve()
exports = board.parent/'exports'
sha = hashlib.sha256(board.read_bytes()).hexdigest()
copper = json.loads((exports/'copper-path-audit.json').read_text(encoding='utf-8'))
electrical = json.loads((exports/'electrical-audit/results.json').read_text(encoding='utf-8'))
assert copper['PCB_sha256'] == electrical['PCB_sha256'] == sha
paths = {tuple(path['from']): path for path in copper['paths'] if path['to'] == ['U1', 42]}
if not {'C75', 'C76'} <= {ref for ref, _ in paths}:
    raise SystemExit('This board does not have the two added VBAT capacitors.')
for ref, pin in [('L1', 2), ('C6', 1), ('C7', 1), ('C75', 1), ('C76', 1)]:
    assert paths[ref, pin]['trace_graph_connected'], f'No routed copper path: {ref}.{pin} to U1.42'

out = exports/'vbat-storage'
out.mkdir(exist_ok=True)
minimum_source = electrical['voltage_corners']['MODEM_3V8']['min_V']
feed_resistance = paths['L1', 2]['estimated_R_20C_ohm'] + .018
cases = []
for with_storage in (False, True):
    for interruption_us in (10, 25, 50, 100):
        onset = .001
        restore = onset + interruption_us*1e-6
        lines = [
            f'Vsupply source 0 {minimum_source}',
            f'Venable enable 0 PWL(0 3.3 {onset-10e-9} 3.3 {onset} 0 {restore} 0 {restore+10e-9} 3.3)',
            'Soutput source feed enable 0 IDEAL_SOURCE',
            '.model IDEAL_SOURCE SW(Ron=0.001 Roff=1e12 Vt=1.65 Vh=0)',
            f'Rfeed feed modem {feed_resistance}',
            f'Vdemand demand 0 PWL(0 .2 {onset-10e-9} .2 {onset} 2 {restore+50e-6} 2 {restore+50.01e-6} .2)',
            'Bload modem 0 I=v(demand)*min(max(v(modem)/3.4,0),1)',
        ]
        for ref, cap_uF, esr in [('C6', 11, .010), ('C7', 11, .010), ('C75', 176, .017), ('C76', 176, .017)]:
            if not with_storage and ref in ('C75', 'C76'):
                continue
            branch = paths[ref, 1]['estimated_R_20C_ohm'] + esr
            lines.extend([f'R{ref} modem {ref} {branch}', f'{ref} {ref} 0 {cap_uF}u'])
        lines.append('.tran 50n .0013')
        label = f'{"added" if with_storage else "ceramic-only"}-{interruption_us}us'
        waveforms, _ = run(label, lines, ['v(modem)', 'v(demand)', 'i(vsupply)'], out)
        window = [i for i, time in enumerate(waveforms['time']) if onset <= time <= restore]
        assert window and abs(waveforms['i(vsupply)'][0]+.2) < .001
        assert max(waveforms['v(demand)'][i] for i in window) >= 1.999
        minimum = min(waveforms['v(modem)'][i] for i in window)
        cases.append({'with_C75_C76': with_storage, 'assumed_source_interruption_us': interruption_us,
                      'minimum_VBAT_V': minimum, 'reaches_below_3p4V': minimum < 3.4})

report = {
    'PCB_sha256': sha,
    'source_voltage_V': minimum_source,
    'assumptions': {
        'current_demand_step_A': [.2, 2],
        'load_below_3p4V': 'Reduced current below the modem operating floor for bounded simulation; only floor crossing is meaningful.',
        'effective_MLCC_uF_each': 11,
        'MLCC_ESR_assumed_ohm_each': .010,
        'C75_C76_min_uF_each': 176,
        'C75_C76_datasheet_ESR_ohm_each': .017,
        'inductor_DCR_ohm': .018,
    },
    'cases': cases,
    'scope': 'Passive sensitivity model. A switched ideal supply, centreline copper estimates and ideal ground are used. No regulator feedback, loop stability, startup, shared branch extraction, ESL, thermal effects or real modem transient are modelled.',
    'still_to_measure': ['SY8089 startup with 440uF added storage', 'regulator stability and current limit', 'ground return', 'VBAT at modem pins during LTE transmit'],
    'manufacturing_ready': False,
}
(out/'results.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
for case in cases:
    print(f'{case["with_C75_C76"]=} {case["assumed_source_interruption_us"]}µs VBAT(min)={case["minimum_VBAT_V"]:.3f}V')
