"""Run actual ngspice RC transient models; never claims UPS/buck/RF validation.

Uses KiCad's bundled ngspice shared library, via Python stdlib ctypes.
"""
from pathlib import Path
import json
from spice_runtime import run as simulate
ROOT=Path(__file__).resolve().parent
def run(name,lines,signals):
    result,_=simulate(name,lines,signals,ROOT/'exports')
    return result
adc=run('battery_adc_rc',['Vbat bat 0 PULSE(0 4.2 1m 1u 1u 100m 200m)','Rtop bat adc 150k','Rbottom adc 0 100k','Cf adc 0 100n','.tran 100u 60m uic'],['v(adc)'])
settling=next(t-.001 for t,v in zip(adc['time'],adc['v(adc)']) if t>.001 and abs(v-1.68)<=.001*1.68)
cases=[]
for resistance in [.05,.15,.30]:
    s=run(f'modem_rc_r{int(resistance*1000)}mohm',[
      '* Ideal 3.8V source + lumped resistance + 484uF ESR reservoir.',
      '* NOT a switching regulator / UPS / RF model.',
      'Vsource src 0 3.8',f'Rpath src modem {resistance}',
      'Resr modem cap 0.05','Cbulk cap 0 484u',
      'Iload modem 0 PULSE(0.3 2 1m 1u 1u 1m 4m)',
      '.tran 1u 4m'],['v(modem)'])
    cases.append(dict(path_resistance_ohm=resistance,minimum_v=min(s['v(modem)']),above_module_minimum_3v4=min(s['v(modem)'])>=3.4,trace=s))
ratio_min=99000/(151500+99000)
ratio_max=101000/(148500+101000)
report={'engine':'KiCad bundled ngspice shared library','battery_adc':{
  'input_v':4.2,'final_adc_v':adc['v(adc)'][-1],'scale':2.5,'tau_ms':6.0,'settling_0_1_percent_ms':settling*1000,
  'recommended_wait_ms':60,'divider_current_uA':4.2/250000*1e6,
  'gated_divider_total_current_uA_approx':4.2/250000*1e6+4.2/100000*1e6,
  'resistor_1_percent_only_reconstruction_error_percent':[(ratio_min/.4-1)*100,(ratio_max/.4-1)*100],
  'adc_error_not_included':True,'mosfet_switch_model':'Ideal enable represented by voltage step; MOSFET leakage/inrush not simulated','trace':adc},
 'modem_transient':{'load_step_A':[.3,2],'pulse_ms':1,'capacitance_uF':484,'esr_ohm':.05,'cases':cases,
 'scope':'Lumped RC model, ideal upstream 3.8V. No converter feedback/switching or cable inductance; pass here is not a hardware pass.'},
 'missing_power_hold_up':{'at_2A_max_0_4V_drop_with_484uF_us':484e-6*.4/2*1e6,'conclusion':'Reservoir cannot bridge milliseconds of UPS switch interruption; actual UPS break must be measured.'},
 'full_ups_simulated':False,'buck_model_simulated':False,'firmware_adc_implemented':False}
(ROOT/'exports/power-simulation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report['battery_adc'].items() if k!='trace'},ensure_ascii=False))
print('Modem RC minimum volts:',[(x['path_resistance_ohm'],round(x['minimum_v'],4)) for x in cases])
