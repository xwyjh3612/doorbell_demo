"""Actual ngspice control-network runs plus independent tolerance calculation.

Comparator is a hysteretic ideal switch; voltage reference is ideal within
the documented TI limits. Neither is an unmodified manufacturer macro-model.
Switching converters, RF and battery electrochemistry are not simulated here.
"""
from pathlib import Path
import sys,json,itertools,math
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parent/'voice_mainboard_v2'))
from spice_runtime import run
d=json.loads((root/'design.json').read_text(encoding='utf8'))
out=root/'exports/ups-simulation';out.mkdir(parents=True,exist_ok=True)
def nodes(v,rt,rb,rf,rp,rd,kind,low=None):
    vp=v if kind=='battery' else max(v,4.2)-.4
    a=1/rt+1/rb+1/rf
    if low is not None:return (v/rt+low/rf)/a,low
    c=1/rp+1/rd+1/rf;det=a*c-1/rf**2
    return ((v/rt*c+vp/rp/rf)/det,(vp/rp*a+v/rt/rf)/det)
def crossing(target,params,kind,low):
    l,h=0.,5.5
    for _ in range(45):
        m=(l+h)/2
        if nodes(m,*params,kind,low)[0]<target:l=m
        else:h=m
    return (l+h)/2
report={'scope':'Control-network behavioral ngspice + independent resistor equations; not converter/complete UPS qualification',
 'reference_limits_v':[1.224,1.259], 'offset_v':[-.003,.003], 'dual_comparator_internal_hysteresis_v':[0,0],
 'reference_source':'TI TLV431B SLVS139Z Table5.7 BI full-temperature; LM393LV SNOSDA4D electrical characteristics +/-3mV full-temperature', 'networks':{},'traces':{},'full_ups_simulated':False}
for kind,controls,cap in [('battery',d['ups_controls']['battery_uv'],'10n'),('external',d['ups_controls']['external_priority'],'1n')]:
    rt=controls['top_ohm'];rb=controls['bottom_ohm'];rf=controls['feedback_ohm']
    rp=controls.get('en_pullup_ohm',controls.get('pullup_ohm'));rd=controls.get('en_pulldown_ohm',controls.get('pulldown_ohm'))
    nom=[rt,rb,rf,rp,rd]
    off=crossing(.62,nom,kind,None);on=crossing(.62,nom,kind,0.)
    ranges={'off':[],'on':[]}
    for signs in itertools.product([-1,1],repeat=8):
        params=[value*(1+sign*tol)for value,sign,tol in zip(nom,signs,[.001,.001,.01,.01,.01])]
        vr=[1.224,1.259][signs[5]>0]
        # 0.1% equal divider arms, using worst possible opposing tolerances.
        ref=vr*(1+signs[6]*.001)/2
        offset=signs[7]*.003
        for hys,vol in itertools.product([0.],[0.,.4]):
            ranges['off'].append(crossing(ref+offset-hys/2,params,kind,None))
            ranges['on'].append(crossing(ref+offset+hys/2,params,kind,vol))
    bounds={k:[min(v),max(v)]for k,v in ranges.items()}
    report['networks'][kind]={'nominal_off_v':off,'nominal_on_v':on,'corner_off_v':bounds['off'],'corner_on_v':bounds['on'],'corner_count_per_edge':len(ranges['on']),
      'external_control_supply_assumption':'max(external,4.2V cell)-0.4V diode' if kind=='external' else'pullup directly from protected cell',
      'sink_vol_bound_v':[0,.4],'dynamic_delay_not_included_in_corner_thresholds':True}
    # Slow triangle sweeps reduce RC slew shifts; capture both hysteresis edges.
    if kind=='battery':wave='PWL(0 4.2 .05 4.2 .45 2.5 .55 2.5 .95 4.2 1 4.2)'
    else:wave='PWL(0 0 .05 0 .45 5.5 .55 5.5 .95 0 1 0)'
    lines=[f'Vsource source 0 {wave}','Vref ref 0 .62',
      f'Rtop source sense {rt}',f'Rbottom sense 0 {rb}',f'Rfeedback result sense {rf}',
      f'Rpullup supply result {rp}',f'Rpulldown result 0 {rd}',f'Cfilter sense 0 {cap}',
      'Bdiff diff 0 V=V(ref)-V(sense)', 'Ssink result 0 diff 0 COMP',
      '.model COMP SW(Ron=1 Roff=1e12 Vt=0 Vh=0)']
    lines += ['Bsupply supply 0 V=V(source)' if kind=='battery' else'Bsupply supply 0 V=max(V(source),4.2)-.4','.tran 50u 1']
    s,_=run('ups_'+kind+'_triangle',lines,['v(source)','v(sense)','v(result)'],out)
    edges=[]
    for i in range(1,len(s['time'])):
        a=s['v(result)'][i-1]>.8;b=s['v(result)'][i]>.8
        if a!=b and s['time'][i]>.05:edges.append({'time_s':s['time'][i],'input_v':s['v(source)'][i],'output_high':b})
    report['networks'][kind]['ngspice_edges']=edges
    report['traces'][kind]={k:v[::20]for k,v in s.items()}
    assert len(edges)==2,(kind,edges)
# Cathode bias: worst 2.5V protected cell, 0.4V diode, largest 6.8k bias.
# Subtract reference divider current and 0.4uA reference-input maximum.
vrmax=1.259
ik=(2.5-.5-vrmax)/(3300*1.01)-vrmax/(20000*.999)-.4e-6
report['reference_bias']={'worst_cathode_uA':ik*1e6,'required_max_minimum_cathode_uA':80,'passes_at_assumed_2v5_cell_and_0v5_diode':ik>=80e-6,
 'diode_drop_and_reference_low_current_error_need_hardware_check':True}
assert ik>=80e-6
temps={'hot':[],'cold':[]}
for a,b,c,e in itertools.product([-1,1],repeat=4):
    rt=9100*(1+.01*a);rs=3300*(1+.01*b);r25=10000*(1+.01*c);beta=3950*(1+.01*e)
    for ratio,name in [(.45,'hot'),(.8,'cold')]:
        resistance=ratio/(1-ratio)*rt-rs
        temps[name].append(1/(1/298.15+math.log(resistance/r25)/beta)-273.15)
report['ntc']={'cold_stop_C':[min(temps['cold']),max(temps['cold'])],'hot_stop_C':[min(temps['hot']),max(temps['hot'])],
 'assumptions':'10k B3950 NTC, R25/B +/-1%, resistors +/-1%, TP4056 TEMP ratios ideal0.45/0.80; IC temperature ratio tolerance not modeled',
 'open_ntc_stops_charge':True,'short_ntc_stops_charge':True,'validation_needed':'Select actual pack NTC; measure trip temperatures and charging termination with backup idle load.'}
report['reservoir']={'capacitance_nominal_uF':480,'capacitance_worst_assumption_uF':376,
 'load_A':2,'drop_at_typical_16us_switch_without_esr_v':2*16e-6/376e-6,
 'max_interruption_for_0v3_drop_us':.3*376e-6/2*1e6,
 'limitation':'TPS2117 16us is typical under specified load; not worst-case proof. Comparator/RC delay, converter response and ESR must be measured.'}
(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in report.items()if k!='traces'},ensure_ascii=False,indent=2))
