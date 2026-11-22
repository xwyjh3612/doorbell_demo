"""Run the archived TI transient model against V5's new modem power circuit.

This simulates the buck only. The upstream UPS is a regulated source assumption;
thermal effects, ML307 RF/firmware and whole-board functions are not modeled.
"""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'voice_mainboard_v2'))
from spice_runtime import run,messages
repo=ROOT.parents[1]
model=repo/'build/ml307-power-reference/tps563201-model/TPS563201_PSPICE_TRANS/TPS563201_TRANS.LIB'
assert model.exists()
out=ROOT/'exports/modem-buck-model'
lines=[
    f'.include "{model.as_posix()}"',
    'Vups upstream 0 DC 5',
    'Rinput upstream vin .05',
    'Rbulk vin cbulk .08',
    'Cbulk cbulk 0 470u',
    'Rcin vin cin .005',
    'Cin cin 0 12u',
    'Ren vin en 100k',
    'Xbuck en 0 sw bst fb vin TPS563201_TRANS PARAMS: STEADY_STATE=0',
    'Cbst bst sw 100n',
    'L1 sw out 2.2u',
    'Rl out vout .04',
    'Rcout vout cout .002',
    'Cout cout 0 24u',
    'Rtop vout fb 39.2k',
    'Rbottom fb 0 10k',
    'Rboard vout modem .02',
    'Rdec modem dec .003',
    'Cdec dec 0 6u',
    'Rload modem 0 18.9',
    'Istep modem 0 PWL(0 0 3m 0 3.01m 1.8 5m 1.8 5.01m 0 6m 0)',
    '.options reltol=.005 abstol=10n vntol=10u method=trap itl4=200',
    '.tran 100n 6m 0 100n',
]
report={'simulator':'ngspice shared library with PSpice compatibility',
    'model_source':'TI archived TPS563201_TRANS Final1.10 30DEC2015',
    'source_url':'https://www.ti.com/product/TPS563201#design-tools-simulation',
    'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
    'scope':'Buck enable-startup with input already5V, followed by load step; no UPS/input-ramp qualification',
    'assumptions':{'UPS_v':5,'input_path_ohm':.05,'inductor_uH':2.2,'inductor_series_ohm':.04,
        'local_effective_output_uF':24,'module_effective_decoupling_uF':6,'PCB_output_path_ohm':.02,
        'baseline_load_resistor_ohm':18.9,'extra_load_step_a':1.8,'model_temperature_effects':False},
    'UPS_qualified':False,'full_motherboard_simulated':False,'manufacturing_ready':False}
try:
    vectors,messages=run('v5_tps563201_nominal',lines,['v(vin)','v(vout)','v(modem)','i(l1)'],out)
    windows={'steady_before_step':[.0025,.00299],'during_load_step':[.003,.005],'recovery':[.005,.006]}
    for name,(a,z) in windows.items():
        selected=[i for i,t in enumerate(vectors['time']) if a<=t<=z]
        report[name]={sig:{'min':min(vectors[sig][i] for i in selected),'max':max(vectors[sig][i] for i in selected)} for sig in ['v(vin)','v(vout)','v(modem)','i(l1)']}
    loaded=report['during_load_step']['v(modem)']
    report['model_completed']=True
    report['modem_voltage_in_3p4_to_4p5_during_step']=loaded['min']>=3.4 and loaded['max']<=4.5
    # Actual simulator samples, with a modest export size for inspection.
    stride=max(1,len(vectors['time'])//12000)
    traces={k:v[::stride] for k,v in vectors.items()}
    (out/'sampled-traces.json').write_text(json.dumps(traces,separators=(',',':'))+'\n',encoding='utf8')
except Exception as e:
    report.update(model_completed=False,error=str(e))
    out.mkdir(parents=True,exist_ok=True)
    (out/'v5_tps563201_nominal.log').write_text('\n'.join(messages)+'\n',encoding='utf8')
out.mkdir(parents=True,exist_ok=True)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
if not report.get('model_completed'):sys.exit(1)
