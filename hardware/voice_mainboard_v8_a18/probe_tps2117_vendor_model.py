"""Verify the unmodified TI TPS2117 transient model runs in ngspice."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
sys.path.insert(0,str(ROOT.parent/'voice_mainboard_v2'))
from spice_runtime import run

MODEL=REPO/'build/voice-mainboard-simulation-20261127/tps2117-ti/TPS2117_PSPICE_TRANS/TPS2117_TRANS.LIB'
OUT=REPO/'build/voice-mainboard-simulation-20261127/vendor-model-probe'
lines=[
    f'.include "{MODEL.as_posix()}"',
    # TI model usage notes cover priority/manual operation, not diode mode.
    # Keep MODE at a valid high level during the supported switchover probe.
    'Vext vin1 0 PWL(0 0 1m 0 1.01m 5 10m 5 10.01m 2 20m 2 20.01m 5 30m 5)',
    'Vbackup vin2 0 PWL(0 0 0.01m 5 30m 5)',
    'Rprtop vin1 pr 100k','Rprbottom pr 0 33.2k','Rstatus out st 10k',
    'XU18 0 vin1 pr st vin1 vin2 out out TPS2117_TRANS',
    'Rload out 0 10','Cload out 0 10u',
    '.options method=gear reltol=.003 abstol=1n vntol=1u',
    '.tran 1u 30m 0 1u',
]
v,log=run('tps2117_unmodified_vendor_probe',lines,['v(out)','v(vin1)','v(vin2)','v(st)','i(vext)','i(vbackup)'],OUT)
def at(sig,t):
    i=min(range(len(v['time'])),key=lambda i:abs(v['time'][i]-t))
    return v[sig][i]
checks={'startup_output':at('v(out)',.006)>4.8,
        'external_selected':at('v(st)',.006)>4,
        'backup_selected':at('v(st)',.016)<.1,
        'backup_output':at('v(out)',.016)>4.8,
        'external_restored':at('v(st)',.026)>4,
        'both_inputs_have_supplied_load':min(v['i(vext)'])<-.4 and min(v['i(vbackup)'])<-.4}
(OUT/'results.json').write_text(json.dumps({'checks':checks,'all_checks_passed':all(checks.values()),
    'simulated_until_s':v['time'][-1],'points':len(v['time']),
    'model':'TI TPS2117 Final 1.10, 17JULY2025, unmodified',
    'source':'https://www.ti.com/lit/zip/SLVMEF2',
    'scope':'Supported priority mode with MODE >=1V; does not verify MODE=0 diode mode'},indent=2),encoding='utf-8')
assert all(checks.values()),checks
print(json.dumps(checks,indent=2),flush=True)
