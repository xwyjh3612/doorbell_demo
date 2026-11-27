"""Run actual ngspice power-up and power-control tests on the saved A18 board.

Uses an UNMODIFIED TI TPS2117 transient model. Other converters use explicitly
declared averaged engineering models and swept assumptions, never masquerading
as manufacturer models or an ESP32/ML307 digital/network simulator.
"""
import datetime
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

import pcbnew as p

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
BOARD=ROOT/'power_relayout_candidate/voice_mainboard_a18_2layer.kicad_pcb'
os.environ['A18_REPAIR_BOARD']=str(BOARD)
sys.path.insert(0,str(ROOT))
from audit_copper_paths import trace_path
sys.path.insert(0,str(ROOT.parent/'voice_mainboard_v2'))
from spice_runtime import run

OUT=BOARD.parent/'exports/powerup-simulation-20261127'
OUT.mkdir(parents=True,exist_ok=True)
MODEL=REPO/'build/voice-mainboard-simulation-20261127/tps2117-ti/TPS2117_PSPICE_TRANS/TPS2117_TRANS.LIB'
board=p.LoadBoard(str(BOARD))
fps={f.GetReference():f for f in board.GetFootprints()}
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
board_hash=sha(BOARD)
parts=json.loads((BOARD.parent/'design.json').read_text(encoding='utf-8'))['parts']
assert len(fps)==len(parts)==150 and board.GetCopperLayerCount()==2

def pins(ref):
    return {d.GetNumber():d.GetNetname()for d in fps[ref].Pads()}
def value(ref):
    text=fps[ref].GetValue()
    aliases={'C8':470e-6,'C19':10e-9,'C28':100e-9,'C29':10e-9,'C20':100e-9,
             'L1':2.2e-6,'L4':2.2e-6,'L5':2.2e-6}
    if ref in aliases:return aliases[ref]
    m=re.match(r'([\d.]+)([kMunp]?)',text)
    assert m,(ref,text)
    return float(m[1])*{'':1,'k':1e3,'M':1e6,'u':1e-6,'n':1e-9,'p':1e-12}[m[2]]
@functools.lru_cache(maxsize=None)
def rpath(a,z):
    q=trace_path(a,z)
    assert q['trace_graph_connected'],q
    return q['estimated_R_20C_ohm']
def at(v,sig,t):
    i=min(range(len(v['time'])),key=lambda i:abs(v['time'][i]-t))
    return v[sig][i]
def minimum(v,sig,a,z):
    return min(y for t,y in zip(v['time'],v[sig])if a<=t<=z)
def maximum(v,sig,a,z):
    return max(y for t,y in zip(v['time'],v[sig])if a<=t<=z)

assert pins('U18')=={'1':'GND','2':'SYS_5V','3':'VIN_PROTECTED','4':'UPS_PR1',
                     '5':'VIN_PROTECTED','6':'BAT_BOOST_5V','7':'SYS_5V','8':'SUPPLY_BAT_N47'}
assert pins('U16')['8']=='CHG_CE' and pins('U16')['4']=='VIN_PROTECTED'
assert pins('Q7')=={'1':'CHG_DISABLE_IO38','2':'GND','3':'CHG_CE'}
assert pins('J23')=={'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NTC'}
assert fps['C5'].IsDNP(), 'Do not count the unpopulated C5 as hold-up capacitance'

path_data={
    'input_to_mux_ohm':rpath(('J1',4),('F1',1))+rpath(('F1',2),('Q6',3))+rpath(('Q6',2),('U18',3)),
    'mux_to_modem_buck_ohm':rpath(('U18',2),('U2',4)),
    'mux_to_esp_buck_ohm':rpath(('U18',2),('U13',4)),
    'boost_to_mux_ohm':rpath(('U15',7),('U18',6)),
    'battery_to_boost_ohm':rpath(('J23',1),('U15',4)),
    'battery_protection_return_ohm':rpath(('J23',2),('U17',2)),
}
modem_target=.6*(1+value('R2')/value('R3'))
esp_target=.6*(1+value('R59')/value('R60'))
boost_target=.6*(1+value('R61')/value('R62'))

# Relate a capacitance to its true BOM value, population and trace path. Ground
# trace/plane resistance and capacitor bias/ESR are explicitly swept assumptions.
caprecords=[]
def caps(lines,net,anchor,scale):
    for ref,f in sorted(fps.items()):
        if not ref.startswith('C') or f.IsDNP():continue
        if set(pins(ref).values())!={net,'GND'}:continue
        if ref in ('C12',):continue # tiny RF capacitor is irrelevant to power hold-up
        cap=value(ref)
        positive=next(d.GetNumber()for d in f.Pads()if d.GetNetname()==net)
        trace=rpath((ref,positive),anchor)
        electrolytic=ref in ('C8','C75','C76')
        effective=cap*(.8 if electrolytic else scale)
        esr=.10 if ref=='C8' else .08 if electrolytic else .012
        lines += [f'R_{ref}_PATH {net} {ref}_CAP {max(.001,trace+esr+.005):.10g}',
                  f'{ref} {ref}_CAP 0 {effective:.10g} IC=0']
        caprecords.append({'ref':ref,'net':net,'nominal_F':cap,'effective_F':effective,
                           'copper_R_ohm':trace,'ESR_assumed_ohm':esr,'populated':True})

results=[]
traces=[]
def sample(case,v,signals):
    stride=max(1,len(v['time'])//1800)
    # Full raw simulator vectors are saved separately; samples are for viewing.
    q={'case':case,'time_ms':[t*1000 for t in v['time'][::stride]]}
    for sig in signals:q[sig]=v[sig][::stride]
    traces.append(q)
    (OUT/(case+'-vectors.json')).write_text(json.dumps(v,separators=(',',':')),encoding='utf-8')

def simulate_supply(case,vin=5,backup=True,scale=.5,source_r=.05,temperature=25,
                    tau=100e-6,stress=False,modem_peak_A=None,model_mode='priority_supported',
                    mux_model='TI_vendor',dead_time_us=16,peak_during_unplug=False,
                    modem_pulse_us=2000,modem_base_A=.2):
    # Actual source path topology: adapter -> PTC -> PMOS -> TPS2117 -> two bucks.
    # PMOS/PTC are bounded resistive approximations here, not transient MOS models.
    if model_mode=='exact_full_unplug':
        ext=f'PWL(0 0 1m 0 1.05m {vin} 15m {vin} 15.05m 0 28m 0 28.05m {vin} 45m {vin})'
    elif model_mode=='priority_supported' and backup:
        ext=f'PWL(0 0 1m 0 1.05m {vin} 15m {vin} 15.05m 2 28m 2 28.05m {vin} 45m {vin})'
    else:
        ext=f'PWL(0 0 1m 0 1.05m {vin} 45m {vin})'
    derate=1+.00393*(temperature-20)
    input_r=(path_data['input_to_mux_ohm']*derate+.025+.05)
    lines=[f'V_ADAPTER_REQUEST ADAPTER_REQUEST 0 {ext}',
        # A smooth finite-current source actually limits source delivery to 2A.
        # Sink capability during the falling waveform is a test-source feature,
        # not a claim that a real unplugged charger can absorb charge.
        f'B_ADAPTER_REG 0 ADAPTER_SOURCE I=2*tanh((V(ADAPTER_REQUEST)-V(ADAPTER))/(2*{source_r}))',
        'Vadapter ADAPTER ADAPTER_SOURCE 0','R_ADAPTER_LEAK ADAPTER 0 1G',
        f'R_MAINPATH ADAPTER VIN_PROTECTED {input_r:.9g}',
        f'R_CHARGER_RESERVOIR VIN_PROTECTED CHG_IN {max(.001,.02):g}', 'C_CHARGER CHG_IN 0 32u',
        f'R70 VIN_PROTECTED UPS_PR1 {value("R70")}',f'R71 UPS_PR1 0 {value("R71")}',
        f'R72 ESP_3V3 SUPPLY_BAT_N47 {value("R72")}',
        f'R_MODEM_INPUT SYS_5V MODEM_IN {path_data["mux_to_modem_buck_ohm"]*derate:.9g}',
        f'R_ESP_INPUT SYS_5V ESP_IN {path_data["mux_to_esp_buck_ohm"]*derate:.9g}',
    ]
    if mux_model=='TI_vendor':
        lines[:0]=[f'.include "{MODEL.as_posix()}"']
        lines += ['XU18 0 VIN_PROTECTED UPS_PR1 SUPPLY_BAT_N47 VIN_PROTECTED BAT_BOOST_5V SYS_5V SYS_5V TPS2117_TRANS']
    else:
        assert mux_model=='bounded_engineering'
        # Separate, visibly labelled diagnostic model. This is NOT a repaired
        # TI macromodel. Datasheet Ron(max at105C)=33mOhm, ideal instantaneous
        # RCB, 1ms startup delay/1.7ms soft start and an externally imposed gap.
        # The 16us typical value and swept 50/100us are not guaranteed maxima.
        # This tests hold-up/input-budget sensitivity, not the IC state machine.
        if backup:
            ext_enable=f'PWL(0 0 2.05m 0 3.75m 1 15m 1 15.001m 0 28.05m 0 {28.05+dead_time_us/1000:.9g}m 1 45m 1)'
            bat_enable=f'PWL(0 0 {15.001+dead_time_us/1000:.9g}m 0 {15.002+dead_time_us/1000:.9g}m 1 28.049m 1 28.05m 0 45m 0)'
        else:
            ext_enable='PWL(0 0 2.05m 0 3.75m 1 45m 1)'
            bat_enable='0'
        lines += [f'VEXT_EN MUX_EXT_EN 0 {ext_enable}',f'VBAT_EN MUX_BAT_EN 0 {bat_enable}',
            'B_MUX_EXT VIN_PROTECTED SYS_5V I=max(V(VIN_PROTECTED)-V(SYS_5V),0)/.033*V(MUX_EXT_EN)',
            'B_MUX_BAT BAT_BOOST_5V SYS_5V I=max(V(BAT_BOOST_5V)-V(SYS_5V),0)/.033*V(MUX_BAT_EN)',
            'B_MUX_ST SUPPLY_BAT_N47 0 I=(1-V(MUX_EXT_EN))*V(SUPPLY_BAT_N47)/5',
            'R_MUX_LEAK SYS_5V 0 1G']
    if backup:
        # This is an explicitly ideal already-running 5V backup source. It is
        # NOT the ETA1096 or battery macro-model; do not claim boost qualification.
        lines += [f'Vbackup BOOST_IDEAL 0 PWL(0 0 6m 0 6.05m {boost_target} 45m {boost_target})',
                  f'R_BOOST_PATH BOOST_IDEAL BAT_BOOST_5V {path_data["boost_to_mux_ohm"]*derate+.025:.9g}']
    else:lines += ['R_BACKUP_ABSENT BAT_BOOST_5V 0 1G']
    caps(lines,'SYS_5V',('U18',2),scale)
    caps(lines,'MODEM_3V8',('U1',42),scale)
    caps(lines,'ESP_3V3',('U7',2),scale)
    modempeak=modem_peak_A if modem_peak_A is not None else 2 if stress else 1
    # External stimuli represent load budgets, not execution of the firmware.
    unplug_m=f'14m {modem_base_A} 14.001m {modempeak} 17m {modempeak} 17.001m {modem_base_A} 'if peak_during_unplug else ''
    unplug_e='14m .15 14.001m .35 17m .35 17.001m .15 'if peak_during_unplug else ''
    first_end=10+modem_pulse_us/1000
    second_end=35.001+modem_pulse_us/1000
    lines += [f'V_MLOAD_CMD MLOAD_CMD 0 PWL(0 {modem_base_A} 9.999m {modem_base_A} 10m {modempeak} {first_end:.9g}m {modempeak} {first_end+.001:.9g}m {modem_base_A} {unplug_m}35m {modem_base_A} 35.001m {modempeak} {second_end:.9g}m {modempeak} {second_end+.001:.9g}m {modem_base_A} 45m {modem_base_A})',
              f'V_ELOAD_CMD ELOAD_CMD 0 PWL(0 .15 9.999m .15 10m .35 12m .35 12.001m .15 {unplug_e}45m .15)',
              'B_MLOAD MODEM_3V8 0 I=V(MLOAD_CMD)*min(max(V(MODEM_3V8)/1,0),1)',
              'B_ELOAD ESP_3V3 0 I=V(ELOAD_CMD)*min(max(V(ESP_3V3)/1,0),1)',
              'B_AUDIO SYS_5V 0 I=.15*min(max(V(SYS_5V)/2,0),1)',
    ]
    # An averaged voltage feedback controller uses the actual FB divider and
    # output L, but control-loop dynamics are engineer-selected and swept.
    # It cannot prove SY8089 loop compensation/switching ripple/current limits.
    for name,inn,out,fb,top,bottom,lref in (
        ('MODEM','MODEM_IN','MODEM_3V8','BUCK_FB','R2','R3','L1'),
        ('ESP','ESP_IN','ESP_3V3','ESP_FB','R59','R60','L5'),
    ):
        setpoint=modem_target if name=='MODEM'else esp_target
        ratio=value(bottom)/(value(top)+value(bottom))
        lines += [f'R_{top} {out} {fb} {value(top)}', f'R_{bottom} {fb} 0 {value(bottom)}',
          f'B_{name}_REF {name}_REF 0 V=.6*min(max((V({inn})-2.5)*10,0),1)',
          f'R_{name}_SOFT {name}_REF {name}_SOFT 1000',f'C_{name}_SOFT {name}_SOFT 0 1u IC=0',
          f'B_{name}_COMMAND {name}_COMMAND 0 V=max((V({name}_SOFT)+3*(V({name}_SOFT)-V({fb})))/{ratio:.10g},0)',
          f'R_{name}_CONTROL {name}_COMMAND {name}_CTRL 1', f'C_{name}_CONTROL {name}_CTRL 0 {tau} IC=0',
          f'B_{name}_DRIVE {name}_DRV 0 V=min(max(V({inn})-.10,0),max(V({name}_CTRL),0))',
          f'R_{name}_FET {name}_DRV {name}_SW .10',
          f'L_{name} {name}_SW {name}_LEND {value(lref)} IC=0',
          f'R_{name}_DCR {name}_LEND {out} .039',
          # Account for the power provided by the dependent voltage source.
          # Converter losses/efficiency are assumptions, not measured silicon.
          f'B_{name}_INPUT {inn} 0 I=max(-I(B_{name}_DRIVE)*V({name}_DRV),0)/(.85*max(V({inn}),1))',
          f'R_{name}_LEAK {out} 0 100k']
    # Reset/boot/externally powered indication/ADC are real RC networks with
    # bounded generic MOS switch models, not proprietary die internals.
    lines += [f'R_EN ESP_3V3 ESP_EN {value("R57")}',f'C56 ESP_EN 0 {value("C56")} IC=0',
      f'R14 ESP_3V3 CALL_BOOT0 {value("R14")}',
      f'R19 ADAPTER EXT_DETECT_GATE {value("R19")}',f'C29 EXT_DETECT_GATE 0 {value("C29")} IC=0',
      f'R20 EXT_DETECT_GATE 0 {value("R20")}',f'R21 ESP_3V3 EXT_PRESENT_N_IO10 {value("R21")}',
      'S_Q5 EXT_PRESENT_N_IO10 0 EXT_DETECT_GATE 0 MOS_DETECT',
      '.model MOS_DETECT SW(Ron=5 Roff=1e12 Vt=2.5 Vh=0)',
      '.options method=gear reltol=.003 abstol=1n vntol=1u', '.tran 2u 45m 0 2u']
    sigs=['v(SYS_5V)','v(MODEM_3V8)','v(ESP_3V3)','v(ESP_EN)','v(CALL_BOOT0)',
          'v(SUPPLY_BAT_N47)','v(EXT_PRESENT_N_IO10)','v(VIN_PROTECTED)','i(Vadapter)']
    if backup:sigs.append('i(Vbackup)')
    v,_=run(case,lines,sigs,OUT)
    sample(case,v,sigs)
    # Only pre/post recovery steady windows and commanded peak windows are
    # scored. Zero rails before insertion must not be interpreted as failures.
    metrics={'system_steady_V':at(v,'v(SYS_5V)',.009),
             'modem_steady_V':at(v,'v(MODEM_3V8)',.009),
             'esp_steady_V':at(v,'v(ESP_3V3)',.009),
             'ESP_EN_at_40ms_V':at(v,'v(ESP_EN)',.040),
             'modem_min_after_start_V':minimum(v,'v(MODEM_3V8)',.008,.044),
             'esp_min_after_start_V':minimum(v,'v(ESP_3V3)',.008,.044),
             'system_min_after_start_V':minimum(v,'v(SYS_5V)',.008,.044),
             'adapter_max_draw_A':-minimum(v,'i(Vadapter)',0,.045),
             'adapter_reverse_transient_A':max(0,maximum(v,'i(Vadapter)',.008,.044)),
             'adapter_reverse_settled_A':max(0,maximum(v,'i(Vadapter)',.023,.026)),
             'ST_on_external_V':at(v,'v(SUPPLY_BAT_N47)',.009),
             'ST_after_drop_V':at(v,'v(SUPPLY_BAT_N47)',.025),
             'external_detect_on_external_V':at(v,'v(EXT_PRESENT_N_IO10)',.009),
             'external_detect_after_drop_V':at(v,'v(EXT_PRESENT_N_IO10)',.025),
             'modem_min_in_drop_window_V':minimum(v,'v(MODEM_3V8)',.014,.018),
             'esp_min_in_drop_window_V':minimum(v,'v(ESP_3V3)',.014,.018)}
    checks={'modem_supply_above_3p4V':metrics['modem_min_after_start_V']>=3.4,
            'esp_supply_above_3p0V':metrics['esp_min_after_start_V']>=3.0,
            'modem_supply_below_4p5V':maximum(v,'v(MODEM_3V8)',.008,.044)<=4.5,
            'esp_supply_below_3p6V':maximum(v,'v(ESP_3V3)',.008,.044)<=3.6,
            'EN_eventually_released':metrics['ESP_EN_at_40ms_V']>=.75*metrics['esp_steady_V'],
            'external_no_settled_backfeed_above_1mA':metrics['adapter_reverse_settled_A']<.001,
            # 10mA acceptance tolerance is 0.5% of the 2A source limit; the
            # solver uses reltol=.003. Keep the observed peak in the report.
            'adapter_draw_limited_to_2A_with_0p5pct_numeric_tolerance':metrics['adapter_max_draw_A']<=2.01}
    checks['external_present_detected_low']=metrics['external_detect_on_external_V']<.02
    inconclusive=model_mode=='exact_full_unplug' and mux_model=='TI_vendor'
    if backup and not inconclusive:
        checks['external_absence_detected_high']=metrics['external_detect_after_drop_V']>.75*metrics['esp_steady_V']
        checks['mux_reports_backup_low']=metrics['ST_after_drop_V']<.05
    record={'case':case,'scenario':'complete external removal under imposed engineering switch-gap envelope'if mux_model=='bounded_engineering'and backup else
            'actual MODE tied to VIN1, complete external removal'if inconclusive else 'supply startup/load test',
            'assumptions':{'adapter_V':vin,'ideal_backup_present':backup,'MLCC_effective_fraction':scale,
              'adapter_and_wire_R_ohm':source_r,'adapter_current_limit_A':2,'copper_temperature_C':temperature,'averaged_buck_time_constant_s':tau,
              'modem_load_peak_A':modempeak,'TPS2117_mode':model_mode,
              'modem_base_load_A':modem_base_A,'modem_pulse_width_us':modem_pulse_us,
              'pulse_profile':'engineer-selected sensitivity stimulus, not a measured modem waveform',
              'peak_during_unplug':peak_during_unplug,
              'mux_model':mux_model,'imposed_dead_time_us':dead_time_us if mux_model=='bounded_engineering'and backup else None,
              'backup_ready_after_external_start_s':.00605 if backup else None,
              'adapter_limit_numeric_tolerance_A':.01},
            'metrics':metrics,'checks':checks,'ngspice_completed':True,
            'status':'INCONCLUSIVE_VENDOR_DIODE_MODE_NOT_MODELLED'if inconclusive else 'PASS_IN_DECLARED_MODEL'if all(checks.values())else 'FAIL_IN_DECLARED_MODEL',
            'scope':('Unmodified TI TPS2117 transient model'if mux_model=='TI_vendor'else
                     'Engineering switch envelope, ideal instantaneous reverse blocking and ideal 5V backup; not manufacturer mux/boost models')+
                     ' plus engineering averaged SY8089 supplies, BOM capacitance/FB/RC and centreline copper resistance; not whole digital board execution'}
    results.append(record)
    print(json.dumps({'case':case,'status':record['status'],'metrics':metrics},indent=2),flush=True)

cases=[
    dict(case='external_5V_no_battery',backup=False),
    dict(case='external_4p5V_no_battery',vin=4.5,backup=False),
    dict(case='external_5p5V_no_battery',vin=5.5,backup=False),
    dict(case='external_5V_priority_backup',backup=True),
    dict(case='external_4p5V_2A_input_budget',vin=4.5,backup=False,modem_peak_A=1.3),
    dict(case='external_4p5V_modem_peak2A_no_battery',vin=4.5,backup=False,stress=True),
    dict(case='weak_adapter_hot_slow_loop',vin=4.5,backup=False,scale=.25,source_r=.25,temperature=80,tau=500e-6,stress=True),
    dict(case='exact_unplug_model_coverage_probe',backup=True,model_mode='exact_full_unplug'),
    dict(case='engineering_unplug_gap16us',backup=True,model_mode='exact_full_unplug',mux_model='bounded_engineering',dead_time_us=16),
    dict(case='engineering_unplug_gap50us',backup=True,model_mode='exact_full_unplug',mux_model='bounded_engineering',dead_time_us=50),
    dict(case='engineering_unplug_gap100us',backup=True,model_mode='exact_full_unplug',mux_model='bounded_engineering',dead_time_us=100),
    dict(case='engineering_unplug_peak1A_gap50us',backup=True,model_mode='exact_full_unplug',mux_model='bounded_engineering',dead_time_us=50,peak_during_unplug=True),
    dict(case='engineering_unplug_peak1p3A_gap100us',backup=True,model_mode='exact_full_unplug',mux_model='bounded_engineering',dead_time_us=100,peak_during_unplug=True,modem_peak_A=1.3),
    dict(case='engineering_4p5V_modem_peak2A',vin=4.5,backup=False,stress=True,mux_model='bounded_engineering'),
    dict(case='engineering_weak_hot_modem_peak2A',vin=4.5,backup=False,scale=.25,source_r=.25,temperature=80,tau=500e-6,stress=True,mux_model='bounded_engineering'),
]
# The user measured about 0.2A during real voice calls. The hardware manual
# documents up to 2A transients at maximum TX power but does not specify their
# width. Sweep widths, retaining 2ms only as a conservative boundary case.
for pulse_us in (20,50,100,500):
    cases.append(dict(case=f'engineering_4p5V_2A_pulse{pulse_us}us',vin=4.5,
        backup=False,stress=True,mux_model='bounded_engineering',modem_pulse_us=pulse_us))
for pulse_us in (50,100):
    cases.append(dict(case=f'vendor_4p5V_2A_pulse{pulse_us}us',vin=4.5,
        backup=False,stress=True,modem_pulse_us=pulse_us))
for pulse_us in (100,500,2000):
    cases.append(dict(case=f'engineering_5V_2A_pulse{pulse_us}us',vin=5,
        backup=False,stress=True,mux_model='bounded_engineering',modem_pulse_us=pulse_us))
cases.append(dict(case='vendor_5V_2A_pulse500us',vin=5,backup=False,stress=True,modem_pulse_us=500))
cases += [
    dict(case='vendor_5V_modem_base0p7A',vin=5,backup=False,modem_base_A=.7,modem_peak_A=.7),
    dict(case='vendor_4p5V_modem_base0p7A',vin=4.5,backup=False,modem_base_A=.7,modem_peak_A=.7),
    dict(case='vendor_5V_modem_base0p8A',vin=5,backup=False,modem_base_A=.8,modem_peak_A=.8),
    dict(case='vendor_5V_base0p7A_peak2A_100us',vin=5,backup=False,modem_base_A=.7,stress=True,modem_pulse_us=100),
    dict(case='vendor_5V_base0p7A_peak2A_500us',vin=5,backup=False,modem_base_A=.7,stress=True,modem_pulse_us=500),
]
selected_cases=set(filter(None,os.environ.get('A18_SIM_CASES','').split(',')))
for q in cases:
    if selected_cases and q['case'] not in selected_cases:continue
    try:simulate_supply(**q)
    except RuntimeError as error:
        results.append({'case':q['case'],'status':'INCONCLUSIVE_SIMULATOR_ABORTED',
                        'ngspice_completed':False,'error':str(error),'requested_case':q})
        print(json.dumps(results[-1]),flush=True)

control_results=[]
for label,cell_V,temp,ntcr in (
    ('controls_cell3p0_room',3.0,25,10000),
    ('controls_cell3p7_room',3.7,25,10000),
    ('controls_cell4p2_room',4.2,25,10000),
    ('controls_cold_minus5',3.7,-5,10000*math.exp(3950*(1/268.15-1/298.15))),
    ('controls_hot45',3.7,45,10000*math.exp(3950*(1/318.15-1/298.15))),
    ('controls_ntc_open',3.7,None,1e15),
    ('controls_ntc_short',3.7,None,.001),
):
    if selected_cases and label not in selected_cases:continue
    lines=['VEXT VIN_PROTECTED 0 5','VCELL BAT_SENSE_IN CELL_NEG '+str(cell_V),
      # Closed battery protector approximation; never short CELL_NEG into GND
      # on the actual board. This submodel does not test protection trips.
      'R_PROTECTION CELL_NEG 0 .02',
      'VESP ESP_3V3 0 3.3',
      'VPAUSE CHG_DISABLE_IO38 0 PWL(0 0 3m 0 3.001m 3.3 6m 3.3 6.001m 0 12m 0)',
      'VADC_ENABLE BAT_ADC_EN9 0 PWL(0 0 3m 0 3.001m 3.3 12m 3.3)',
      f'R68 VIN_PROTECTED CHG_CE {value("R68")}',f'R69 CHG_DISABLE_IO38 0 {value("R69")}',
      'S_Q7 CHG_CE 0 CHG_DISABLE_IO38 0 NCTRL',
      '.model NCTRL SW(Ron=5 Roff=1e12 Vt=2.5 Vh=0)',
      f'R65 VIN_PROTECTED BAT_TEMP {value("R65")}',f'R66 BAT_TEMP 0 {value("R66")}',
      f'R67 BAT_TEMP CELL_NTC .001',f'R_PACK_NTC CELL_NTC CELL_NEG {ntcr:.12g}',
      f'R64 CHG_PROG 0 {value("R64")}',
      f'R73 ESP_3V3 CHG_ACTIVE_N {value("R73")}',f'R74 ESP_3V3 CHG_FULL_N {value("R74")}',
      # Charger output is an explicit CC/CV engineering approximation, governed
      # by the real TEMP/CE/RPROG values, not a TP4056 manufacturer model.
      'V_CHARGER_MON VIN_PROTECTED CHARGER_IN 0',
      f'B_TP4056 CHARGER_IN BAT_SENSE_IN I=(V(CHG_CE)>1.2 && V(VIN_PROTECTED)-V(BAT_SENSE_IN)>.15 && '
      f'((V(BAT_TEMP)/V(VIN_PROTECTED)>.45 && V(BAT_TEMP)/V(VIN_PROTECTED)<.8) || V(BAT_TEMP)<.01))'
      f'*min({1200/value("R64")},max((4.2-V(BAT_SENSE_IN))/.1,0))',
      f'R15 BAT_SENSE_IN BAT_GATE {value("R15")}',f'R16 BAT_ADC_EN9 0 {value("R16")}',
      'S_Q4 BAT_GATE 0 BAT_ADC_EN9 0 NCTRL',
      'S_Q3 BAT_SENSE_IN BAT_DIV_SW BAT_SENSE_IN BAT_GATE PCTRL',
      '.model PCTRL SW(Ron=10 Roff=1e12 Vt=1.5 Vh=0)',
      f'R17 BAT_DIV_SW BAT_ADC2 {value("R17")}',f'R18 BAT_ADC2 0 {value("R18")}',
      f'C28 BAT_ADC2 0 {value("C28")} IC=0',
      'R_DIV_LEAK BAT_DIV_SW 0 1G',
      # R17||R18 and C28 have a ~6ms time constant. Observe >6 tau
      # after enabling at 3ms, rather than mistaking its RC settling for a fault.
      '.options method=gear reltol=.003 abstol=1n', '.tran 2u 45m 0 2u']
    signals=['v(CHG_CE)','v(BAT_TEMP)','v(BAT_ADC2)','v(CELL_NEG)','i(V_CHARGER_MON)']
    v,_=run(label,lines,signals,OUT)
    sample(label,v,signals)
    ratio=at(v,'v(BAT_TEMP)',.002)/5
    metrics={'battery_source_V':cell_V,'TEMP_to_VCC_ratio':ratio,
       'CE_GPIO38_low_V':at(v,'v(CHG_CE)',.002),'CE_GPIO38_high_V':at(v,'v(CHG_CE)',.004),
       'ADC_disabled_V':at(v,'v(BAT_ADC2)',.002),
       'ADC_enabled_at_12ms_V':at(v,'v(BAT_ADC2)',.012),
       'ADC_enabled_at_40ms_V':at(v,'v(BAT_ADC2)',.040),
       'ADC_divider_ratio':value('R18')/(value('R17')+value('R18')),
       'ADC_RC_time_constant_ms':value('R17')*value('R18')/(value('R17')+value('R18'))*value('C28')*1000,
       'charge_current_GPIO_low_mA':1000*at(v,'i(V_CHARGER_MON)',.002),
       'charge_current_GPIO_high_mA':1000*at(v,'i(V_CHARGER_MON)',.004)}
    checks={'CE_default_high':metrics['CE_GPIO38_low_V']>4.9,
      'CE_can_pause':metrics['CE_GPIO38_high_V']<.01,
      'ADC_disabled_near_zero':metrics['ADC_disabled_V']<.02,
      'ADC_settles_near_actual_divider_at_40ms':abs(metrics['ADC_enabled_at_40ms_V']-metrics['ADC_divider_ratio']*cell_V)<.02,
      'charge_pauses_with_GPIO_high':abs(metrics['charge_current_GPIO_high_mA'])<.01}
    if label in ('controls_cold_minus5','controls_hot45','controls_ntc_open'):
        checks['charge_pauses_for_TEMP_fault']=abs(metrics['charge_current_GPIO_low_mA'])<.01
    if label in ('controls_cell3p0_room','controls_cell3p7_room'):
        checks['100mA_setting_applied']=abs(metrics['charge_current_GPIO_low_mA']-100)<1
    if label=='controls_cell4p2_room':
        checks['CC_CV_model_stops_at_4p2V']=abs(metrics['charge_current_GPIO_low_mA'])<.01
    record={'case':label,'metrics':metrics,'checks':checks,'ngspice_completed':True,
      'status':'KNOWN_LIMIT_NTC_SHORT_DISABLES_TEMP_MONITOR'if label=='controls_ntc_short'else
      'PASS_IN_DECLARED_MODEL'if all(checks.values())else 'FAIL_IN_DECLARED_MODEL',
      'scope':'Actual TEMP/CE/ADC resistor/capacitor topology with generic switches and declared TP4056 CC/CV approximation; battery is a voltage source, not a chemical-cell model'}
    control_results.append(record)
    print(json.dumps({'case':label,'status':record['status'],'metrics':metrics}),flush=True)

# Model evidence is part of the report; no passing simulator run can replace a
# missing semiconductor model or certify firmware/network behaviour.
unique_caps={q['ref']:q for q in caprecords}
report={'product':'语音对讲主板','created_at':datetime.datetime.now().astimezone().isoformat(),
    'PCB_sha256':board_hash,'schematic_sha256':sha(BOARD.with_suffix('.kicad_sch')),
    'simulator':'ngspice shared library shipped with KiCad 9; actual transient runs',
    'TI_TPS2117_model':{'file':str(MODEL.relative_to(REPO)),'sha256':sha(MODEL),
       'url':'https://www.ti.com/lit/zip/SLVMEF2','version':'Final 1.10, 17JULY2025',
       'unmodified':True,'supported':'startup, priority/manual switching, RCB, ST, Ron',
       'not_covered':'temperature dependence and MODE-low diode operation'},
    'load_evidence':{'user_measurement':'User reported about0.2A previously and updated current reading to about0.7A; electronic clamp meter bandwidth, capture mode and measurement node not recorded',
       'manufacturer_document':'build/ml307c-seller-review-20261125/ML307C_硬件设计手册_AT版本适用.txt',
       'manufacturer_statement':'Maximum 4G TX power may draw up to 2A transiently; recommend supply capability above2A and at least two220uF capacitors on VBAT',
       'manufacturer_pulse_width_specified':False,
       'test_pulse_widths_us':[20,50,100,500,2000],
       'interpretation':'2A is a transient stress amplitude, not measured sustained voice-call consumption. Applied widths are assumptions; no board defect can be inferred solely from an assumed2ms profile'},
    'path_resistances_20C_ohm':path_data,'nominal_rail_targets_V':{'MODEM':modem_target,'ESP':esp_target,'BOOST':boost_target},
    'population_aware_capacitors':list(unique_caps.values()),'DNP_C5_excluded':True,
    'cases':results,'control_cases':control_results,'selected_cases':sorted(selected_cases),
    'full_board_function_simulated':False,'manufacturing_ready':False,
    'remaining_model_limits':['No manufacturer SY8089 or ETA1096 switching/thermal macro-model used',
      'No TP4056 chemical-cell charging macro-model used',
      'ESP32/ML307 firmware, RF, network, audio and USB are not executed',
      'Copper estimates exclude ground plane current distribution and connector contact variation',
      'Capacitor DC-bias/ESR, converter control dynamics and sources are explicit assumptions',
      'Exact external unplug enters diode mode absent from the TI model; that result is inconclusive, not proof of a board fault']}
assert sha(BOARD)==board_hash,'Simulation must never change the board'
if selected_cases and (OUT/'results.json').exists():
    previous=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
    assert previous['PCB_sha256']==board_hash,'Do not merge simulations from different PCB versions'
    report['cases']=[q for q in previous['cases']if q['case'] not in selected_cases]+results
    report['control_cases']=[q for q in previous['control_cases']if q['case'] not in selected_cases]+control_results
    combined={q['ref']:q for q in previous['population_aware_capacitors']}
    combined.update(unique_caps)
    report['population_aware_capacitors']=list(combined.values())
    if (OUT/'sampled-traces.json').exists():
        traces=[q for q in json.loads((OUT/'sampled-traces.json').read_text(encoding='utf-8'))if q['case'] not in selected_cases]+traces
(OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'sampled-traces.json').write_text(json.dumps(traces,separators=(',',':')),encoding='utf-8')
print('Simulation suite saved:',OUT,flush=True)
