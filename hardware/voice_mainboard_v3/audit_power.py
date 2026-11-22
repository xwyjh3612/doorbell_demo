"""Measure saved switching paths and publish a conditional input-power budget.

Track-only local lengths are actual CAD measurements. Loss/trace allowances
are explicit estimates, not measured waveforms or validated closed-loop models.
"""
from pathlib import Path
import json,math,heapq
import pcbnew as p
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
fps={f.GetReference():f for f in b.GetFootprints()}
def xy(item):return (round(p.ToMM(item.GetPosition().x),6),round(p.ToMM(item.GetPosition().y),6))
def pad(ref,n):return next(pd for pd in fps[ref].Pads()if pd.GetNumber()==str(n))
def local_path(a,z,net,region):
    graph={}
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA)or t.GetNetname()!=net or t.GetLayer()!=p.F_Cu:continue
        aa=tuple(round(p.ToMM(v),6)for v in (t.GetStart().x,t.GetStart().y));zz=tuple(round(p.ToMM(v),6)for v in (t.GetEnd().x,t.GetEnd().y))
        if not all(region[0]<=pt[0]<=region[2]and region[1]<=pt[1]<=region[3]for pt in [aa,zz]):continue
        length=math.dist(aa,zz);width=p.ToMM(t.GetWidth())
        # 1oz 35um, copper rho at 20C. Returns trace-only resistance.
        resistance=1.724e-8*(length/1000)/(width/1000*35e-6)
        for left,right in [(aa,zz),(zz,aa)]:graph.setdefault(left,[]).append((right,length,width,resistance))
    start,end=xy(pad(*a)),xy(pad(*z));heap=[(0,start,[])];seen=set()
    while heap:
        cost,node,route=heapq.heappop(heap)
        if node in seen:continue
        seen.add(node)
        if node==end:return {'from':a,'to':z,'net':net,'layer':'F.Cu','length_mm':round(cost,4),
          'min_track_width_mm':min(s[1]for s in route),'trace_resistance_20C_mohm':round(sum(s[2]for s in route)*1000,4),
          'segments':[{'length_mm':round(s[0],4),'width_mm':s[1]}for s in route]}
        for nxt,length,width,resistance in graph.get(node,[]):
            if nxt not in seen:heapq.heappush(heap,(cost+length,nxt,route+[(length,width,resistance)]))
    return {'from':a,'to':z,'net':net,'track_only_path_found':False,'note':'Pad area / zone / via paths are not represented in this local endpoint graph.'}
paths=[local_path(('U9',4),('C41',1),'BAT_SENSE_IN',(10,52,27,65)),
 local_path(('U9',5),('L3',2),'UPS_SW',(5,50,27,65)),
 local_path(('U9',7),('C42',1),'UPS_BACKUP_5V',(10,50,27,65))]
losses={'jack_both_contacts_ohm':.100,'ptc_R1max_ohm':.025,'reverse_fet_max_low_gate_ohm':.045,
 'mux_max_5V_high_temp_ohm':.033,'trace_via_return_allowance_ohm':.050,'power_shunt_allowance_ohm':.040}
protection=losses['jack_both_contacts_ohm']+losses['ptc_R1max_ohm']+losses['reverse_fet_max_low_gate_ohm']
scenarios=[]
for vin in [4.5,5.0,5.5]:
    for current in [1.0,1.5,2.0]:
        bus=vin-current*sum(losses.values())
        # Alternative loads; NOT a statement of actual module consumption.
        # Charging runs upstream of the mux and consumes 100mA from input.
        modem_power=3.792*2/.9
        system_power=5*.35/.9
        required=modem_power+system_power+vin*.1
        usable=vin*current-current*current*sum(losses.values())
        scenarios.append({'connector_v':vin,'input_a':current,'protected_v_before_mux':round(vin-current*protection,4),
          'power_bus_v_estimate':round(bus,4),'path_loss_w_estimate':round(current*current*sum(losses.values()),4),
          'power_after_series_loss_w':round(usable,4),'example_2A_modem_plus_350mA_system_and_100mA_charge_w':round(required,4),
          'example_continuous_load_power_budget_pass':usable>=required})
report={'source':'Saved KiCad V3 board; component resistance limits plus explicit allowances',
 'local_switching_paths':paths,'input_series_resistance':losses,'scenarios':scenarios,
 'capacitor_review':'C41 is the local 22uF VIN bypass; C40 is additional input bulk farther away. Removing or relocating C40 is not required solely from its VIN distance.',
 'conclusion':'5V/2A is a nominal adapter baseline, not a proven simultaneous continuous 2A modem / loud audio / radar specification. The 4.5V boundary and modem rail dropout remain unqualified.',
 'assumptions':['90% efficiency on each branch is an assumption, not a measured minimum.',
 'No actual copper-zone spreading / ground-return / connector or shunt contact resistance extraction.',
 'No pulsed modem current profile, converter startup, control loop or thermal model.',
 'TPS2117 RON bound is specified at 5V; lower-voltage maximum needs separate characterization.'],
 'hardware_validated':False,'manufacturing_release':False}
(root/'exports/power-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'local_paths':paths,'continuous_full_load_example_pass_at_5V2A':next(x for x in scenarios if x['connector_v']==5 and x['input_a']==2)['example_continuous_load_power_budget_pass']},ensure_ascii=True))
