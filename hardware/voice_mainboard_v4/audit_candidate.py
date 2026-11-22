"""Meaningful engineering checks, not a claim of complete motherboard simulation.

Checks native board versus design pin contract and the C-DL library, models
control resistor networks in ngspice, and calculates reference/resistor corners.
Modem, radio, real converter startup, battery and USB stacks are not modeled.
"""
from pathlib import Path
import sys, json, itertools, math
import pcbnew as p

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
parts={q['ref']:q for q in data['parts']}
board=p.LoadBoard(str(ROOT/'voice_mainboard_v4.kicad_pcb'))
fps={f.GetReference():f for f in board.GetFootprints()}
assert board.GetCopperLayerCount()==2
assert parts['U1']['mpn']=='ML307C-DL' and parts['U1']['lcsc']=='C48972417'
source=json.loads((ROOT/'sources/ml307c-dl-library.json').read_text(encoding='utf8'))
assert len(list(fps['U1'].Pads()))==109
modem_pads={pd.GetNumber():pd for pd in fps['U1'].Pads()}
origin=fps['U1'].GetPosition()
assert abs(fps['U1'].GetOrientationDegrees())<.001
for expected in source['pads']:
    actual=modem_pads[expected['number']]
    observed=[p.ToMM(actual.GetPosition().x-origin.x),p.ToMM(actual.GetPosition().y-origin.y),
              p.ToMM(actual.GetSize().x),p.ToMM(actual.GetSize().y),actual.GetOrientationDegrees()]
    target=[expected[k]for k in ['x_mm','y_mm','width_mm','height_mm','rotation_deg']]
    assert all(abs(a-e)<.001 or i==4 and abs((a-e)%360)<.001 for i,(a,e) in enumerate(zip(observed,target))),expected['number']
for ref,q in parts.items():
    for pad in fps[ref].Pads():
        assert str(pad.GetNetname())==q['pins'].get(pad.GetNumber(),''),(ref,pad.GetNumber())
    if not q['dnp']:
        assert fps[ref].GetLayer()==p.F_Cu
assert all(parts['U1']['names'][k][0]==v for k,v in source['pin_names'].items())
assert all(not parts['U1']['pins'][str(n)] for n in [62,63,64,65,77,86,87])
assert [parts['J18']['pins'][str(n)] for n in range(1,5)]==['GND','DEBUG_ESP_TX43','DEBUG_ESP_RX44','VIN_DC']
assert [parts['J16']['pins'][str(n)] for n in range(1,5)]==['RADAR_5V','GND','RADAR_RX6','RADAR_TX8']
assert all(pad.GetNetname()=='POWER_BUS' for pad in fps['U1'].Pads() if pad.GetNumber() in ['42','43'])
assert all(p.ToMM(pad.GetDrillSize().x)>=.3 for f in fps.values() for pad in f.Pads() if pad.GetAttribute()==p.PAD_ATTRIB_PTH)
assert all(parts[r]['dnp'] for r in ['R28','R29','R31'])
assert all(not parts[r]['dnp'] for r in ['R26','R27','R30'])

def sense(v,rt,rb,rf,rp,diode,external=False,low=None):
    supply=max(v,4.2)-diode if external else v-diode
    a=1/rt+1/rb+1/rf
    if low is not None:return (v/rt+low/rf)/a
    b=1/rp+1/rf
    return (v/rt*b+supply/rp/rf)/(a*b-1/rf**2)
def edge(ref,params,external,low):
    a,b=0.,5.5
    for _ in range(48):
        m=(a+b)/2
        if sense(m,*params,external,low)<ref:a=m
        else:b=m
    return (a+b)/2

report={'scope':'Native connectivity/selection checks; independent DC equations and behavioral ngspice controls only',
        'native_pin_contract_passed':True,'all_installed_parts_front':True,'C_DL_library_consistent':True,
        'C_DL_native_pad_coordinates_sizes_angles_match_library':True,
        'full_motherboard_simulated':False,'manufacturing_ready':False,'networks':{}}
sys.path.insert(0,str(ROOT.parent/'voice_mainboard_v2'))
from spice_runtime import run
out=ROOT/'exports/control-model';out.mkdir(exist_ok=True)
for key,external,tols in [('battery_uv',False,[.001,.001,.01,.01]),('external_priority',True,[.01,.01,.01,.01])]:
    d=data['ups_controls'][key]
    vals=[d['top_ohm'],d['bottom_ohm'],d['feedback_ohm'],d['pullup_ohm']]
    nominal=[*vals,.4]
    corners={'off':[],'on':[]}
    for signs in itertools.product([-1,1],repeat=8):
        parameters=[v*(1+s*t) for v,s,t in zip(vals,signs,tols)]
        vref=[1.224,1.259][signs[4]>0]
        top,bottom=10000*(1+signs[5]*.001),10000*(1+signs[6]*.001)
        ref=vref*bottom/(top+bottom)+signs[7]*.003
        for diode,vol in itertools.product([.15,.5],[0,.4]):
            pars=[*parameters,diode]
            corners['off'].append(edge(ref,pars,external,None))
            corners['on'].append(edge(ref,pars,external,vol))
    wave='PWL(0 4.2 .05 4.2 .45 3.0 .55 3.0 .95 4.2 1 4.2)' if not external else 'PWL(0 0 .05 0 .45 5.5 .55 5.5 .95 0 1 0)'
    circuit=[f'Vsource source 0 {wave}','Vref ref 0 .62',
             f'Rtop source sense {vals[0]}',f'Rbottom sense 0 {vals[1]}',f'Rfeedback result sense {vals[2]}',
             f'Rpullup supply result {vals[3]}','Cfilter sense 0 10n',
             'Bdiff diff 0 V=V(ref)-V(sense)','Ssink result 0 diff 0 COMP',
             '.model COMP SW(Ron=1 Roff=1e12 Vt=0 Vh=0)',
             'Bsupply supply 0 V=max(V(source),4.2)-.4' if external else 'Bsupply supply 0 V=V(source)-.4',
             '.tran 50u 1']
    vectors,_=run('v4_'+key,circuit,['v(source)','v(sense)','v(result)'],out)
    edges=[]
    for i in range(1,len(vectors['time'])):
        high=vectors['v(result)'][i]>.8
        if high!=(vectors['v(result)'][i-1]>.8) and vectors['time'][i]>.05:
            edges.append({'input_v':vectors['v(source)'][i],'output_high':high,'time_s':vectors['time'][i]})
    assert len(edges)==2,(key,edges)
    report['networks'][key]={'nominal_off_v':edge(.62,nominal,external,None),
                            'nominal_on_v':edge(.62,nominal,external,0),
                            'corner_off_v':[min(corners['off']),max(corners['off'])],
                            'corner_on_v':[min(corners['on']),max(corners['on'])],
                            'ngspice_edges':edges,
                            'model_limits':'Ideal reference and comparator switch; no real delay, ripple, load-drop or transistor gate dynamics. External primary PG modeled only by connectivity.'}

# Bias valid down to assumed 2.5V cell with 0.5V diode drop; full DC voltage
# compliance and reference load stability still need the selected parts measured.
current=(2.5-.5-1.259)/(3300*1.01)-1.259/(20000*.999)-.4e-6
assert current>=80e-6
report['reference_bias']={'worst_cathode_uA':current*1e6,'datasheet_minimum_current_max_uA':80,
                          'assumed_cell_v':2.5,'assumed_diode_drop_v':.5,'passes_assumptions':True}
uvmin=report['networks']['battery_uv']['corner_off_v'][0]
report['battery_drop_budget']={'min_control_trip_v':uvmin,'modem_minimum_v':3.4,
    'total_allowable_drop_before_trip_v':uvmin-3.4,
    'mux_R_on_max_ohm_at_3v3_105C_200mA_datasheet':.033,
    'mux_loss_at_assumed_2A_v':2*.033,
    'remaining_for_pack_PFET_copper_connectors_v':uvmin-3.4-2*.033,
    'qualification':'2A extrapolation and threshold budget only; load transients and actual battery capacity not qualified.'}
report['cannot_verify_without_hardware']=['C-DL voltage/timing and current limits from full manufacturer HW manual',
    'Current AT/MQTT/UDP firmware compatibility and USB descriptors/ESP32 driver',
    'Actual low-input startup, converter loops, thermal behavior and battery handover under call load',
    'RF/USB routing and real assembly fit; long call tests on new hardware']
(ROOT/'exports/candidate-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='cannot_verify_without_hardware'},ensure_ascii=False,indent=2))
