"""Reproducible V2 electrical review. Never reports whole-product simulation PASS.

No serial access, firmware changes, flashing, or circuit/model rewriting.
MOS models below are deliberately generic envelopes, not manufacturer models.
The original TI PSpice model is downloaded into ignored build/, unchanged.
"""
from pathlib import Path
import hashlib, itertools, json, sys, urllib.request, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from html import escape
from spice_runtime import run

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
OUT=ROOT/'exports/function-simulation'
OUT.mkdir(parents=True,exist_ok=True)
LOGS=WORK/'build/v2-simulation-logs'
LOGS.mkdir(parents=True,exist_ok=True)
MODEL_URL='https://www.ti.com/lit/zip/SLVMBD1'
MODEL_DIR=WORK/'build/ml307-power-reference/tps563201-model'
MODEL=MODEL_DIR/'TPS563201_PSPICE_TRANS/TPS563201_TRANS.LIB'
report={'generated_at':datetime.now().astimezone().isoformat(),
        'engine':'KiCad 9 bundled ngspice shared library, PSpice compatibility / XSPICE',
        'whole_product_pass':False,'manufacturing_ready':False,'firmware_changed':False,
        'sources':{'ml307':'https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/M307R_Hardware_Datasheet.pdf',
                   'buck_datasheet':'https://www.ti.com/lit/ds/symlink/tps563201.pdf',
                   'buck_original_model':MODEL_URL,
                   'translator':'https://www.ti.com/lit/ds/symlink/sn74axc1t45.pdf'},
        'model_limits':[
            'Generic LEVEL=1 MOS envelope: VTO=0.8/1.5/2.5V, KP=0.005 A/V^2, explicit body diode. No vendor temperature model.',
            'PMOS envelope: VTO=-0.8/-1.5/-2.5V, KP=0.002 A/V^2. Off leakage is an injected 0/1uA scenario, not a guarantee.',
            'External GPIO uses 0.25/0.75 of 3.3V as conservative digital thresholds; actual ESP pin specifications must be checked.',
            'ML307 PWRKEY/RESET internal pull-up modeled as assumed 100k to VBAT / 1.8V. Actual internal values not supplied.',
            'RC power model has ideal upstream supply. No switching control, cable inductance, RF, thermal or UPS path model.',
            'MOS sweeps are parameter scenarios, not a temperature, production tolerance or lifetime qualification.'
        ],'sections':{}}

netxml=ROOT/'exports/voice_mainboard_v2.net.xml'
xml=ET.parse(netxml).getroot()
nets={(n.attrib['ref'],n.attrib['pin']):net.attrib['name'].removeprefix('/')
      for net in xml.findall('./nets/net') for n in net.findall('node')}
values={p.attrib['ref']:p.findtext('value') for p in xml.findall('./components/comp')}
model_values={'R1':'100k','R2':'39.2k','R3':'10k','R14':'10k','R15':'100k','R16':'100k',
              'R17':'150k','R18':'100k','R19':'100k','R20':'100k','R21':'10k','R25':'10k',
              'C27':'100n','C28':'100n','C29':'10n','C30':'100n','C19':'10n',
              'C6':'22u','C7':'22u','C8':'220u','C9':'220u','C10':'10u',
              'Q1':'2N7002','Q2':'2N7002','Q3':'BSS84','Q4':'2N7002','Q5':'2N7002'}
for ref,expected in model_values.items():
    if values[ref].split()[0]!=expected:raise RuntimeError(f'{ref} changed; revise simulation model: {values[ref]} != {expected}')
def expect(ref,pins):
    return [{'ref':ref,'pin':pin,'expected':name,'actual':nets.get((ref,pin)),
             'pass':nets.get((ref,pin))==name} for pin,name in pins.items()]

# Independent interface expectations derived from device pin tables and active firmware.
checks=[]
for ref,pins in {
    'U1':{'7':'MODEM_PWRKEY_N','11':'M_SIM_DATA','12':'M_SIM_RESET','13':'M_SIM_CLK','14':'SIM_VCC',
          '15':'MODEM_RESET_N','17':'M_RX_1V8','18':'M_TX_1V8','19':'M_DTR_1V8','24':'MODEM_1V8',
          '35':'RF_ANT','42':'MODEM_3V8','43':'MODEM_3V8','59':'M_USB_DP','60':'M_USB_DM','61':'USB_DETECT_5V'},
    'U2':{'1':'GND','2':'BUCK_SW','3':'SYS_5V','4':'BUCK_FB','5':'BUCK_EN','6':'BUCK_BST'},
    'U3':{'1':'ESP_3V3','2':'GND','3':'ESP_TX17','4':'M_RX_1V8','5':'ESP_3V3','6':'MODEM_1V8'},
    'U4':{'1':'ESP_3V3','2':'GND','3':'ESP_RX18','4':'M_TX_1V8','5':'GND','6':'MODEM_1V8'},
    'U5':{'1':'ESP_3V3','2':'GND','3':'ESP_DTR4','4':'M_DTR_1V8','5':'ESP_3V3','6':'MODEM_1V8'},
    'J14':{'1':'ESP_3V3','2':'GND','3':'I2S_MIC_BCLK14','4':'I2S_MIC_WS13','5':'I2S_MIC_DATA12'},
    'J15':{'1':'SYS_5V','2':'GND','3':'I2S_AMP_BCLK15','4':'I2S_AMP_WS16','5':'I2S_AMP_DATA7'},
    'J16':{'1':'RADAR_5V','2':'GND','3':'RADAR_TX_TO_IO6','4':'RADAR_RX_FROM_IO8'},
    'J18':{'1':'GND','2':'DEBUG_ESP_TX43','3':'DEBUG_ESP_RX44','4':'TTL_5V'},
    'JP3':{'1':'SYS_5V','2':'ESP_5V','3':'TTL_5V'},
    'J12':{'1':'SERVICE_USB_VBUS','2':'SERVICE_USB_DM','3':'SERVICE_USB_DP','4':'GND'},
    'J13':{'28':'ESP_USB_DM19','29':'ESP_USB_DP20','30':'GND'},
    'R26':{'1':'M_USB_DP','2':'SERVICE_USB_DP'},'R27':{'1':'M_USB_DM','2':'SERVICE_USB_DM'},
    'R28':{'1':'M_USB_DP','2':'ESP_USB_DP20'},'R29':{'1':'M_USB_DM','2':'ESP_USB_DM19'},
    'R30':{'1':'SERVICE_USB_VBUS','2':'USB_DETECT_5V'},'R31':{'1':'SYS_5V','2':'USB_DETECT_5V'},
    'Q3':{'1':'BAT_GATE','2':'BAT_SENSE_IN','3':'BAT_DIV_SW'},
    'Q4':{'1':'ADC_EN_IO9','2':'GND','3':'BAT_GATE'},
    'R17':{'1':'BAT_DIV_SW','2':'ADC_BAT_IO2'},'R18':{'1':'ADC_BAT_IO2','2':'GND'},
    'SW1':{'1':'BOOT_BTN_IO0','2':'GND'},'SW2':{'1':'ESP_EN','2':'GND'},
}.items():checks+=expect(ref,pins)
active=(WORK/'components/codec_board/board_cfg.txt').read_text(encoding='utf-8').split('Board: CUSTOM_AUDIO_BOARD')[-1]
fw_checks=[{'name':'microphone active I2S','pass':'bclk:14,ws:13,din:12' in active.replace(' ','')},
           {'name':'amplifier active I2S','pass':'bclk:15,ws:16,dout:7' in active.replace(' ','')},
           {'name':'modem TX17 RX18 DTR4 921600','pass':'AtModem::Detect(GPIO_NUM_17, GPIO_NUM_18, GPIO_NUM_4, 921600)' in (WORK/'main/network_4g.cpp').read_text(encoding='utf-8')},
           {'name':'radar RX6 / reserved TX8','pass':all(s in (WORK/'main/radar_presence.c').read_text(encoding='utf-8') for s in ['RADAR_RX GPIO_NUM_6','RADAR_UNUSED_TX GPIO_NUM_8'])}]
report['sections']['interfaces']={'checks':checks,'firmware_pin_checks':fw_checks,
    'pass':all(c['pass'] for c in checks+fw_checks),
    'scope':'Static independent KiCad netlist / pin contract only. No UART timing or firmware execution.',
    'source_hashes':{str(p.relative_to(WORK)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     [netxml,WORK/'components/codec_board/board_cfg.txt',WORK/'main/network_4g.cpp',WORK/'main/radar_presence.c']}}

NM='.model NENV NMOS (LEVEL=1 VTO={vto} KP=0.005 LAMBDA=0.01 RD=2 RS=2 CGSO=100p CGDO=100p)'
PM='.model PENV PMOS (LEVEL=1 VTO=-{vto} KP=0.002 LAMBDA=0.01 RD=5 RS=5 CGSO=50p CGDO=50p)'
DIODE='.model BODY D (IS=1p N=1.2 RS=1 CJO=20p)'
traces={}
adc=[]
for idx,(vb,vt,tolerance) in enumerate(itertools.product([3.0,3.7,4.2],[0.8,1.5,2.5],[-1,0,1])):
    rt=150000*(1+.01*tolerance);rb=100000*(1-.01*tolerance)
    deck=[f'Vbat bat 0 {vb}','Ven ctl 0 PULSE(0 3.3 1m 1u 1u 79m 160m)',
          'Rgate bat gate 100k','Ren ctl 0 100k','Mn gate ctl 0 0 NENV','Dn 0 gate BODY',
          'Mp switched gate bat bat PENV','Dp switched bat BODY',
          f'Rtop switched adc {rt}',f'Rbottom adc 0 {rb}','Cfilter adc 0 100n',
          NM.format(vto=vt),PM.format(vto=vt),DIODE,'.tran 100u 140m']
    name=f'adc_envelope_{idx:02}'
    d,_=run(name,deck,['v(adc)','v(switched)','v(gate)','i(vbat)'],OUT)
    at60=next(v for t,v in zip(d['time'],d['v(adc)']) if t>=.061)
    final=d['v(adc)'][-1]
    onsteady=next(v for t,v in zip(d['time'],d['v(adc)']) if t>=.078)
    target=vb*rb/(rt+rb)
    adc.append({'battery_v':vb,'vto_abs_v':vt,'resistor_corner':tolerance,
                'adc_at_60ms_v':at60,'reconstructed_v':at60*2.5,
                'reconstruction_error_percent':(at60*2.5/vb-1)*100,
                'settled_0_1_percent_at_60ms':abs(at60-onsteady)/onsteady<=.001,
                'dc_switch_and_divider_error_percent':(onsteady/target-1)*100,
                'reconstruction_within_3_percent_model_target':abs(at60*2.5/vb-1)<=.03,
                'off_after_60ms_v':final,'maximum_adc_v':max(d['v(adc)'])})
    if vb==4.2 and vt==1.5 and tolerance==0:traces['adc']=d
leakage=[]
for leak in [0,1e-6]:
    d,_=run(f'adc_off_leak_{int(leak*1e6)}uA',[
        'Vbat bat 0 4.2','Ven ctl 0 0','Rgate bat gate 100k','Ren ctl 0 100k',
        'Mn gate ctl 0 0 NENV','Dn 0 gate BODY','Mp switched gate bat bat PENV','Dp switched bat BODY',
        f'Ileak bat switched {leak}','Rtop switched adc 150k','Rbottom adc 0 100k','Cfilter adc 0 100n',
        NM.format(vto=1.5),PM.format(vto=1.5),DIODE,'.tran 100u 60m'],['v(adc)','i(vbat)'],OUT)
    leakage.append({'assumed_off_leakage_uA':leak*1e6,'off_adc_v':d['v(adc)'][-1],
                    'battery_current_uA':-d['i(vbat)'][-1]*1e6})
# Dead-ESP clamp is an envelope for injection, not the actual ESP ESD protection model.
d,_=run('adc_esp_unpowered_leak_envelope',[
    'Vbat bat 0 4.2','Ileak bat switched 1u','Rtop switched adc 150k','Rbottom adc 0 100k',
    'Cfilter adc 0 100n','Dclamp adc rail BODY','Vdead rail 0 0',DIODE,'.tran 100u 60m'],['v(adc)','i(vdead)'],OUT)
report['sections']['battery_adc']={'cases':adc,'off_leakage_envelope':leakage,
    'unpowered_esp_envelope':{'adc_v':d['v(adc)'][-1],'rail_injection_uA':-d['i(vdead)'][-1]*1e6,
        'limit':'Injected 1uA hypothetical leak, generic diode; no real ESP protection/power sequencing model.'},
    'acceptance':'60ms settles within 0.1% of actual model steady state; reconstructed battery voltage within chosen 3% circuit-only target. ADC errors excluded.',
    'pass_within_generic_on_envelope':all(c['settled_0_1_percent_at_60ms'] and c['reconstruction_within_3_percent_model_target'] for c in adc),
    'real_adc_accuracy_verified':False,'firmware_adc_implemented':False}

detect=[]
for idx,(vt,vb) in enumerate(itertools.product([.8,1.5,2.5],[4.5,5,5.25])):
    d,_=run(f'input_detect_envelope_{idx}',[
        f'Vext ext 0 PULSE(0 {vb} 1m 1u 1u 19m 40m)','Vesp rail 0 3.3',
        'Rtop ext gate 100k','Rbottom gate 0 100k','Cf gate 0 10n',
        'Rpull rail present 10k','Mn present gate 0 0 NENV','Dn 0 present BODY',
        NM.format(vto=vt),DIODE,'.tran 10u 30m'],['v(gate)','v(present)'],OUT)
    high=next(v for t,v in zip(d['time'],d['v(present)']) if t>=.015)
    off=d['v(present)'][-1]
    detect.append({'vto_v':vt,'input_v':vb,'present_low_v':high,'removed_high_v':off,
                   'recognizes_presence':high<=.825,'recognizes_removal':off>=2.475})
    if vt==2.5 and vb==5:traces['detector']=d
report['sections']['external_power_detector']={'cases':detect,
    'pass_within_generic_envelope':all(c['recognizes_presence'] and c['recognizes_removal'] for c in detect),
    'issue':'R19=R20=100k reduces 5V to 2.5V at gate. High-threshold envelope does not pull GPIO low reliably.',
    'action':'Revise resistor ratio / choose a specified logic-level switch or a PGOOD/comparator after UPS selection. Verify slow ramps and actual thresholds.',
    'precise_undervoltage_detection':False}

buttons=[]
for label,rt,cap in [('boot',10000,100e-9),('esp_en',10000,100e-9)]:
    d,_=run(label+'_rc',[
        'Vrail rail 0 3.3','Vpress control 0 PULSE(0 3.3 2m 1u 1u 5m 30m)',
        f'Rpull rail node {rt}',f'Cfilter node 0 {cap}',
        'Sbutton node 0 control 0 SWITCH','.model SWITCH SW(RON=1 ROFF=1e12 VT=1.65 VH=.01)',
        '.tran 10u 15m'],['v(node)'],OUT)
    release=.007001
    th=next(t-release for t,v in zip(d['time'],d['v(node)']) if t>release and v>=2.475)
    buttons.append({'name':label,'pressed_v':min(d['v(node)']),'release_to_0_75Vdd_ms':th*1000,
                    'pass_in_ideal_switch_model':min(d['v(node)'])<.825 and d['v(node)'][-1]>2.475})
    if label=='boot':traces['button']=d
report['sections']['boot_reset']={'cases':buttons,'pass_in_ideal_switch_model':all(c['pass_in_ideal_switch_model'] for c in buttons),
    'limitations':'1ms RC does not remove multi-ms contact bounce. Firmware debounce and real dev-board EN parallel RC must be checked. No ESP boot-ROM simulation.'}

controls=[]
for label,voltage,duration,vto in itertools.product(['pwrkey','modem_reset'],[1.8,3.8],[.35],[.8,2.5]):
    if label=='pwrkey' and voltage!=3.8:continue
    if label=='modem_reset' and voltage!=1.8:continue
    duration=2.5 if label=='pwrkey' else .35
    d,_=run(f'{label}_{int(vto*10)}',[
        f'Vmodule rail 0 {voltage}',f'Ven gate 0 PULSE(0 3.3 .6 1u 1u {duration} 10)',
        'Rinternal rail node 100k','Rgate gate 0 100k','Cf node 0 10n',
        'Mn node gate 0 0 NENV','Dn 0 node BODY',NM.format(vto=vto),DIODE,
        f'.tran 1m {duration+.7}'],['v(node)'],OUT)
    low=next(v for t,v in zip(d['time'],d['v(node)']) if t>=.7);idle=d['v(node)'][-1]
    window=[v for t,v in zip(d['time'],d['v(node)']) if .61<=t<=.6+duration-.01]
    electrical_pass=all(-.3<=v<=.5 for v in window) and idle>=.75*voltage
    controls.append({'name':label,'vto_v':vto,'low_v':low,'released_v':idle,
                     'low_duration_s':duration,'starts_after_power_s':.6,
                     'minimum_tested_window_v':min(window),'maximum_tested_window_v':max(window),
                     'pass_in_assumed_pullup_model':electrical_pass})
report['sections']['modem_control']={'cases':controls,'pass_in_assumed_pullup_model':all(c['pass_in_assumed_pullup_model'] for c in controls),
    'firmware_controls_implemented':False,'limits':'Internal pull-ups assumed. Model only checks MOS open-drain low / release. Actual boot, shutdown, recovery and RESET timing need module tests.'}

loadcases=[]
for r in [.05,.15,.30]:
    d,_=run(f'modem_supply_rc_{int(r*1000)}mohm',[
        '* Ideal source / resistance / reservoir, NOT a converter or UPS model',
        'Vsupply src 0 3.8',f'Rpath src modem {r}',
        'Resr modem cap .05','Cbulk cap 0 494u',
        'Iload modem 0 PULSE(.3 2 1m 1u 1u 1m 4m)',
        '.tran 1u 4m'],['v(modem)'],OUT)
    loadcases.append({'resistance_ohm':r,'min_v':min(d['v(modem)']),
                      'above_module_minimum':min(d['v(modem)'])>=3.4})
    traces['supply_'+str(r)]=d
fb=[]
for vr,top,bottom,ibias in itertools.product([.749,.768,.787],[.999,1.001],[.999,1.001],[-.1e-6,.1e-6]):
    # DC relation with specified VFB current; no switching behavior.
    fb.append(vr*(1+39200*top/(10000*bottom))+ibias*39200*top)
report['sections']['modem_power']={'rc_cases':loadcases,'capacitance_nominal_uF':494,
    'cap_note':'C6+C7+C8+C9+C10 = 494uF; previous 484uF illustration excluded C10. Bias/tolerance/temperature derating absent.',
    'nominal_feedback_v':.768*(1+39200/10000),'datasheet_dc_output_range_v':[min(fb),max(fb)],
    'worst_case_static_path_budget_before_ripple_ohm':(min(fb)-3.4)/2,
    'hold_up_with_494uF_2A_0_4V_drop_us':494e-6*.4/2*1e6,
    'model_pass_all_resistance_scenarios':all(c['above_module_minimum'] for c in loadcases),
    'design_review_issue':'TI recommended output capacitor range is 20-68uF. Draft directly parallels ~494uF. Stability/startup/limit behavior not validated; cannot approve this buck BOM.',
    'reference':'TPS563201 datasheet section 7.2.2.3 / ML307 hardware supply section 3.2.3',
    'limits':'DC feedback calculation is not a regulated transient or thermal test. RC cases diagnose hypothetical paths, not actual board resistance.'}
hold,_=run('modem_capacitor_only_hold_up',[
    '* 494uF only, precharged 3.8V; source removed, ideal constant 2A load',
    'Cbulk modem 0 494u IC=3.8','Iload modem 0 2',
    '.tran 100n 150u uic'],['v(modem)'],OUT)
report['sections']['modem_power']['capacitor_only_crosses_3v4_us']=next(t*1e6 for t,v in zip(hold['time'],hold['v(modem)']) if v<3.4)

# Real TI model: original file stays local, recorded with its hash. A partial run is BLOCKED.
buck={'original_model_url':MODEL_URL,'model_unchanged':True,'model_temperature_simulated':False,'cases':[]}
try:
    if not MODEL.exists():
        archive=WORK/'build/ml307-power-reference/tps563201-unencrypted.zip'
        archive.parent.mkdir(parents=True,exist_ok=True)
        request=urllib.request.Request(MODEL_URL,headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(request,timeout=40) as response:archive.write_bytes(response.read())
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                target=(MODEL_DIR/info.filename).resolve()
                if not target.is_relative_to(MODEL_DIR.resolve()):raise RuntimeError('Unsafe model archive path')
            z.extractall(MODEL_DIR)
    buck['sha256']=hashlib.sha256(MODEL.read_bytes()).hexdigest()
    include=MODEL.relative_to(WORK).as_posix()
    common=[f'.include "{include}"','Ren vin en 100k','Cbst bst sw 100n','Cin vin 0 44u',
            'Rdcr outl out .04','Resr out cap .05','Rfbtop out fb 39.2k','Rfbbottom fb 0 10k','Rload out 0 12.6']
    for name,options,initial in [
        ('startup','.options method=gear reltol=.003',False),
        ('steady_gear','.options method=gear reltol=.01 abstol=1u vntol=10u',True),
        ('steady_shunt','.options method=gear reltol=.01 rshunt=1e12 cshunt=1e-12',True),
        ('steady_trap','.options method=trap reltol=.01 gmin=1e-10',True)]:
        deck=common+([ 'Vinput vin 0 5','Xbuck en 0 sw bst fb vin TPS563201_TRANS PARAMS: STEADY_STATE=1',
                       'Lout sw outl 2.2u IC=.3','Cout cap 0 494u IC=3.75','.ic v(out)=3.75 v(fb)=.762',
                       '.tran 100n 1m 0 100n uic'] if initial else
                     ['Vinput vin 0 PWL(0 0 100u 5)','Xbuck en 0 sw bst fb vin TPS563201_TRANS',
                      'Lout sw outl 2.2u','Cout cap 0 494u','.tran 200n 4m 0 100n'])+[options]
        try:
            d,_=run('ti_buck_'+name,deck,['v(out)','i(lout)'],LOGS)
            buck['cases'].append({'name':name,'simulation_completed':True,
                                  'min_v':min(d['v(out)']),'max_v':max(d['v(out)']),
                                  'last_v':d['v(out)'][-1],'electrical_acceptance':'Unqualified; requires startup/steady-state criteria and model validation.'})
        except RuntimeError as error:
            buck['cases'].append({'name':name,'simulation_completed':False,'reason':str(error)})
        (OUT/('ti_buck_'+name+'.cir')).write_text('TI official model attempt\n'+'\n'.join(deck)+'\n.end\n',encoding='utf-8')
    buck['status']='BLOCKED' if any(not c['simulation_completed'] for c in buck['cases']) else 'REQUIRES_REVIEW'
except Exception as error:buck.update(status='BLOCKED',reason=str(error))
report['sections']['ti_buck_model']=buck

report['coverage']=[
    {'function':'引脚、UART电平转换方向、I2S和雷达接口','status':'STATIC_PASS' if report['sections']['interfaces']['pass'] else 'FAIL','evidence':'Independent KiCad netlist / active firmware pin comparison','next':'921600 UART signals and I2S/radar real hardware verification'},
    {'function':'电池采样打开、关闭、60ms等待、分压容差','status':'ENVELOPE_PASS' if report['sections']['battery_adc']['pass_within_generic_on_envelope'] else 'FAIL','evidence':'27 generic MOS/RC parameter cases + leakage scenarios','next':'Actual part leakage / ESP ADC calibration / chosen cell discharge curve'},
    {'function':'外部电源插拔检测','status':'ENVELOPE_FAIL' if not report['sections']['external_power_detector']['pass_within_generic_envelope'] else 'ENVELOPE_PASS','evidence':'9 generic MOS cases; 2.5V gate high-threshold corner','next':'Revise hardware before routing and repeat tests'},
    {'function':'BOOT/呼叫按钮、ESP EN复位','status':'IDEAL_SWITCH_PASS' if report['sections']['boot_reset']['pass_in_ideal_switch_model'] else 'FAIL','evidence':'RC switch transient; no boot-ROM','next':'Firmware debounce / actual board RC / manual TTL flash'},
    {'function':'ML307开机、复位控制电路','status':'ENVELOPE_PASS' if report['sections']['modem_control']['pass_in_assumed_pullup_model'] else 'FAIL','evidence':'Open-drain transistor pull-down / release with assumed internal pull-up','next':'Firmware control not implemented; real module timing and power cycle'},
    {'function':'模组2A负载、电源路径阻抗','status':'RC_FAIL_AT_300mOHM','evidence':'Ideal supply RC scenario, not actual board measurement','next':'Select regulator and prove supply voltage remains >=3.4V'},
    {'function':'TPS563201真实降压启动及闭环','status':buck['status'],'evidence':'Official TI PSpice model run attempts; end-time validation','next':'Use model-supported PSpice / TI validation; resolve ~494uF output capacitance'},
    {'function':'长期充电、UPS切换、保护、备用电池续航','status':'BLOCKED','evidence':'UPS chip / cell / protection not selected','next':'Supply exact chip and battery specs, design power path then simulate / measure'},
    {'function':'插拔TTL及双电源防倒灌','status':'STATIC_ONLY','evidence':'JP3 only powers ESP branch; no simultaneous links permitted','next':'Dev-board USB power path unknown; external USB backfeed needs validation'},
    {'function':'ML307电源重启/残压放电','status':'MISSING_DESIGN','evidence':'No explicit VBAT discharge path; module guide requires <1.8V for >=100ms','next':'Design and verify discharge / restart sequence; do not improvise during calls'},
    {'function':'反接、短路、ESD、EMC、散热','status':'UNVERIFIED','evidence':'UPS/adapter protection unknown; no PCB routes or thermal model','next':'Freeze BOM / complete protection and PCB stack-up / laboratory tests'},
    {'function':'SIM、USB、RF、天线及整机尺寸','status':'STATIC_ONLY','evidence':'Pins / candidate footprints only; unrouted links remain','next':'Part signoff, RF50Ω / USB90Ω routing, real enclosure fit and signal tests'},
    {'function':'4G入网、MQTT/WSS、双向语音、锁屏接听、掉线原因上报','status':'REAL_HARDWARE_REQUIRED','evidence':'No functional ESP/ML307/radio/OS model; existing physical call tests are separate','next':'Physical integration tests; cannot claim product pass from circuit simulation'},
    {'function':'生命体征检测、声学音量','status':'REAL_HARDWARE_REQUIRED','evidence':'Radar algorithms / biological sensing / speaker cavity have no supplied validated model','next':'Real radar and acoustic tests on final assembled enclosure'}]
next_steps=[
    '实测921600串口、I2S和雷达；核对所用器件时序',
    '实测开关漏电、ADC校准及最终电池放电曲线',
    '修改阈值裕量后重新仿真，并实测慢速掉压与插拔',
    '核对固件去抖、开发板并联RC和TTL手动刷机',
    '控制固件尚未实现；实测模组开关机、复位及电源循环',
    '确认稳压器和整条供电路径在峰值负载下仍高于3.4V',
    '在模型支持的PSpice环境验证，并处理约494µF输出网络',
    '提供芯片、电池及保护资料，补齐电源路径后再验证',
    '核对开发板USB电源结构和实际倒灌；不能同时短接两侧',
    '补齐残压放电设计及重新上电时序，验证低于1.8V至少100ms',
    '冻结BOM、完成保护/布线/叠层并进行实物测试',
    '封装签核，RF50Ω/USB90Ω布线，外壳尺寸及实物信号验证',
    '用实际硬件、手机和蜂窝网络完成全流程与持续通话验收',
    '在最终装配外壳上实测雷达检测和喇叭音量/音质',
]
for c,text in zip(report['coverage'],next_steps):c['next']=text
report['coverage'].insert(1,{'function':'USB Host/维修通路及互斥贴装',
    'status':'STATIC_PASS' if report['sections']['interfaces']['pass'] else 'FAIL',
    'evidence':'19 independent J12/J13/R26-R31 pin checks; population contract checked by verify_design.py',
    'next':'完成90Ω差分、ESD与最终连接器；实测枚举和USB通话，不能同时连接两个主机'})

report['reproducibility']={'run_from':'repository root','command':'python hardware/voice_mainboard_v2/simulate_functions.py',
    'requires':'Python 3.11+, Windows KiCad bundled ngspice under build/cad-tools/kicad; optional matplotlib==3.10.7 under build/cad-tools/sim-python',
    'netlist_sha256':hashlib.sha256(netxml.read_bytes()).hexdigest(),
    'model_download':'Original TI unencrypted file is local build-only. See URL and SHA256; never modify manufacturer model.',
    'generic_decks':'exports/function-simulation/*.cir','full_ti_diagnostics':'build/v2-simulation-logs/*.log'}
(OUT/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

adc_error=[c['reconstruction_error_percent'] for c in adc]
power=report['sections']['modem_power']
status_names={'STATIC_PASS':'静态核对通过','ENVELOPE_PASS':'通用模型情景通过','ENVELOPE_FAIL':'通用模型情景失败',
              'IDEAL_SWITCH_PASS':'理想开关模型通过','RC_FAIL_AT_300mOHM':'300mΩ情景失败','BLOCKED':'尚不能验证',
              'REQUIRES_REVIEW':'仿真输出待审查','STATIC_ONLY':'仅有静态检查','MISSING_DESIGN':'设计缺项',
              'UNVERIFIED':'未验证','REAL_HARDWARE_REQUIRED':'需实机验证','FAIL':'失败'}
rows=['| 功能 | 本轮结论 | 后续验证 |','| --- | --- | --- |']
for c in report['coverage']:rows.append('| '+c['function']+' | '+status_names[c['status']]+' | '+c['next']+' |')
validation=json.loads((ROOT/'exports/validation.json').read_text(encoding='utf-8'))
md=f'''# 语音对讲主板V2 仿真审查报告

生成时间：{report['generated_at']}。对象：现有100×75mm未布线草图、ML307R-DL贴主板、UPS接口预留。

**本版未通过整机验收，不能据此下单生产。** 本轮完成了现有可建模电路的仿真与功能覆盖盘点；ESP32/ML307固件、真实4G网络、UPS及声学/雷达行为没有完整仿真。电路模型通过只代表对应假设下的结果。

## 本轮执行结果

- {len(checks)}项独立接口引脚核对、{len(fw_checks)}项当前固件引脚核对均通过；KiCad现有报告为ERC {validation['schematic_erc_violations']}、摆放DRC {validation['placement_drc_violations']}、{validation['connected_unique_pin_net_mappings']}项网表/焊盘匹配，仍有{validation['unrouted_links']}处未布线连接。
- 新增USB Host/维修口的19项独立引脚核对；默认贴R26/R27/R30，Host组R28/R29/R31不贴，互斥贴装由网表验证器检查。USB未布线、未枚举或通话实测；这一项不是USB信号仿真。
- 49组ngspice瞬态计算完成到指定结束时间：27组采样参数、3组漏电/ESP无电情景、9组外部输入检测、2组按钮RC、4组模组控制、3组供电阻抗、1组电容储能。完成计算不代表每组都通过电气判据。
- 4组TI原厂TPS563201 PSpice模型尝试均提前中止，统一标为未验证。记录实际停止时间和错误，不把部分波形算作通过。
- 本仿真脚本不修改设备固件、不打开串口、不刷机；官方协议和主动丢旧UDP包策略保持原样。当前AT恢复固件的实机回归另见[实机记录](../../tests/at_recovery_batch_20261121.md)。

## 必须处理的设计项

1. **外部电源检测阈值缺乏裕量。** R19/R20均为100k，5V仅给门极2.5V。9组通用模型情景中3组未识别输入存在；VTO=2.5V、输入5V时GPIO仍约3.30V。需要调整电路，并按最终器件规格验证慢速掉压、输入插拔和温度。当前检测器不能用来可靠判断欠压。
2. **降压候选BOM尚未验证。** 约494µF直接并到输出，超出TI数据表20–68µF推荐范围。必须验证闭环稳定性、启动、轻载、2A突发和限流；目前TI模型与ngspice的瞬态计算中止阻塞这项验证，不能确认候选芯片适用。
3. **ML307供电循环缺少残压放电设计。** 厂家要求重新上电前VBAT低于1.8V保持至少100ms。草图没有专门放电路径或已确认时序，不能保证电源闪断后的重新启动。
4. **UPS芯片、电池和保护电路未确定。** 充电、边充边用、无缝切换、过流/短路、低电关机、温升和续航均尚不能验证。494µF在2A负载下从3.8V降到3.4V的仿真时间约{power['capacitor_only_crosses_3v4_us']:.1f}µs，不能承担毫秒级UPS供电中断。
5. **PCB尚未布线。** RF、USB、大电流、接地、回流路径、EMC、散热、实际封装/外壳尺寸尚未完成；摆放DRC没有替代这些工作。

## 功能覆盖表

'''+ '\n'.join(rows)+f'''

## 电池采样详细结果

假设普通4.2V满充单节锂电池。27组场景：电池3.0/3.7/4.2V、NMOS/PMOS阈值绝对值0.8/1.5/2.5V、分压电阻相反方向的±1%容差。

开启后60ms相对各模型的实际稳态均达到0.1%范围；电池还原误差为{min(adc_error):.3f}%至{max(adc_error):.3f}%，满足本轮选择的电路部分±3%粗略采样目标。这个误差包括模型开关压降和分压电阻，**没有包括ESP32 ADC、温度或器件真实漏电误差**。等待时间的判据与直流还原误差分别记录，避免混淆。

在假设关闭漏电1µA时，ADC节点约0.100V；不能把通用MOS模型的关闭结果当成零漏电保证。ESP无电测试使用通用二极管钳位模型，真实ADC保护结构仍需实测。电量百分比、剩余时间和低电关机需要选定电池放电曲线与固件实现。

## 模组供电详细结果

理想3.8V源、等效供电电阻、494µF/50mΩ电容，负载从0.3A升至2A并保持1ms：

| 等效路径电阻 | 最低供电 | 相对3.4V要求 |
| --- | --- | --- |
'''+ '\n'.join(f'| {c["resistance_ohm"]*1000:.0f}mΩ | {c["min_v"]:.4f}V | {"满足该情景" if c["above_module_minimum"] else "失败"} |' for c in loadcases)+f'''

上述电阻是人为设置的情景，不是现有设备或PCB的测量值；不能据此确定掉话原因。

39.2k/10k、0.1%反馈电阻，参考电压749–787mV、VFB输入电流±0.1µA的直流计算范围为{min(fb):.4f}–{max(fb):.4f}V。按最低端计算，2A时给路径压降留下约{power['worst_case_static_path_budget_before_ripple_ohm']*1000:.1f}mΩ总预算；纹波、负载调整率、线缆电感及温升会继续消耗裕量。整机5V电流还包括ESP32、功放和雷达，适配器与UPS需测总峰值。

## 官方降压模型尝试

模型来源：[TI SLVMBD1]({MODEL_URL})；数据表：[TPS563201](https://www.ti.com/lit/ds/symlink/tps563201.pdf)。原始文件保持不变，仅下载至被Git忽略的build目录。

模型SHA256：`{buck.get('sha256','下载未完成')}`。

'''+ '\n'.join('- '+c['name']+'：'+('完整运行，电气结果待验收' if c['simulation_completed'] else c['reason']) for c in buck['cases'])+'''

这些运行因模型/求解器的收敛或兼容问题中止。记录为未验证，不能用这份结果判定实物降压器稳定性。后续应在模型支持的PSpice环境验证，或取得TI对所选输出网络的确认并做台架测试。没有平滑或改写原厂模型来制造通过结果。

## 从这份报告到打样

1. 提供实际UPS芯片型号、参考原理图/测试板、电池化学体系及放电能力；补齐电源路径、保护与掉电行为。
2. 修正外部检测阈值裕量；验证降压器输出网络；补齐ML307电源循环/放电时序。
3. 确认采购BOM、ML307封装、插座/SIM卡座尺寸、ESP开发板安装方法和外壳内尺寸。
4. 完成叠层、RF/USB/电源布线，所有未连接项清零并复核接地、回流、温升与ESD。
5. 打样后测5V/VBAT峰值、启动、切换、过流和低电行为，再做双向通话、反复上下电、后台/锁屏接听及雷达测试。测量应保留示波器波形和串口日志。

## 文件与复现

- [波形图](exports/function-simulation/waveforms.png)
- [浏览器覆盖表](exports/function-simulation/index.html)
- [数值结果与原始失败原因](exports/function-simulation/results.json)
- [仿真脚本](simulate_functions.py)，从仓库根目录运行。需要本项目KiCad ngspice；绘图依赖matplotlib 3.10.7。
- SPICE输入在`exports/function-simulation/*.cir`；TI完整运行日志在`build/v2-simulation-logs/*.log`。TI输入中的模型路径相对仓库根目录。
- [ML307R硬件手册](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/M307R_Hardware_Datasheet.pdf)，供电章节、开关机章节与复位章节是本次判据来源。

仿真没有执行ESP32应用、WebRTC、MQTT/WSS服务器、Android后台策略、真实蜂窝网络、雷达内部算法或声学模型。相关功能保留为实机验收项，报告不提供虚构的整机通过率。
'''
(ROOT/'仿真审查报告.md').write_text(md,encoding='utf-8')
html_rows=[]
for c in report['coverage']:
    cls='bad' if c['status'] in ['ENVELOPE_FAIL','RC_FAIL_AT_300mOHM','FAIL','MISSING_DESIGN'] else ('good' if 'PASS' in c['status'] else 'pending')
    html_rows.append(f'<tr><td>{escape(c["function"])}</td><td class="{cls}">{escape(status_names[c["status"]])}</td><td>{escape(c["next"])}</td></tr>')
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>语音对讲V2 仿真审查</title><style>body{font:16px "Microsoft YaHei",sans-serif;background:#edf2f7;color:#24374b;margin:0}main{max-width:1320px;margin:auto;padding:28px}h1{font-size:30px}p{line-height:1.7}.card{background:white;border-radius:14px;padding:22px;margin:20px 0}.warning{background:#fff0d6;border-left:5px solid #bb7625;padding:16px}table{border-collapse:collapse;width:100%}th,td{padding:14px 10px;border-bottom:1px solid #dde5ed;text-align:left;vertical-align:top;line-height:1.5}.bad{color:#b83035;font-weight:bold}.good{color:#14675b}.pending{color:#8d651e}img{width:100%;height:auto}a{color:#14675b}</style>
<main><h1>语音对讲主板V2 · 仿真审查</h1><p class="warning">整机尚未通过验收，禁止据此下单生产。49组电路瞬态完成计算，外部电源检测及高阻供电情景存在失败；TI降压模型、UPS及实机功能尚未验证。</p>
<div class="card"><h2>已执行的检查</h2><p>__CHECKS__项接口引脚与__FW_CHECKS__项现有固件引脚核对通过，其中19项为USB预留接口。电池采样、按钮RC和开漏控制仅在对应模型假设下通过；本仿真不接触实机固件。</p><p><a href="../../仿真审查报告.md">完整文字报告</a> · <a href="results.json">全部数值与模型失败原因</a> · <a href="../review.html">板图与原理图预览</a></p></div>
<div class="card"><h2>电路波形</h2><img src="waveforms.png" alt="电池采样、2A供电负载、输入检测失败及BOOT按钮的实际ngspice波形"></div>
<div class="card"><h2>功能覆盖与下一步</h2><table><thead><tr><th>功能</th><th>结果范围</th><th>还需完成</th></tr></thead><tbody>__ROWS__</tbody></table></div>
<p>模型来源为TI官方PSpice模型及明确标注的通用MOS/RC模型。真实4G通话、UPS保护、PCB信号完整性和声学/雷达功能须另做实机验证。</p></main></html>'''.replace('__ROWS__',''.join(html_rows)).replace('__CHECKS__',str(len(checks))).replace('__FW_CHECKS__',str(len(fw_checks)))
(OUT/'index.html').write_text(html,encoding='utf-8')

sys.path.insert(0,str(WORK/'build/cad-tools/sim-python'))
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10})
    fig,axes=plt.subplots(2,2,figsize=(13,8.5),layout='constrained')
    ax=axes[0,0];d=traces['adc'];ax.plot([t*1000 for t in d['time']],d['v(adc)'],color='#16716b')
    ax.axhline(1.68,color='#999999',ls='--',lw=1);ax.axvline(61,color='#888',ls=':',lw=1)
    ax.set(title='电池4.2V：开启/关闭采样（通用MOS模型）',xlabel='时间 ms',ylabel='ADC节点 V')
    ax=axes[0,1]
    for r in [.05,.15,.30]:
        d=traces['supply_'+str(r)];ax.plot([t*1000 for t in d['time']],d['v(modem)'],label=f'{int(r*1000)} mΩ')
    ax.axhline(3.4,color='#c83939',ls='--',label='模组最低3.4V');ax.legend()
    ax.set(title='0.3→2A负载：理想电源RC情景',xlabel='时间 ms',ylabel='模组供电 V')
    ax=axes[1,0];d=traces['detector']
    ax.plot([t*1000 for t in d['time']],d['v(gate)'],label='MOS门极')
    ax.plot([t*1000 for t in d['time']],d['v(present)'],label='GPIO检测')
    ax.axhline(.825,color='#c83939',ls='--',label='低电平判据0.825V');ax.legend()
    ax.set(title='5V输入、VTO=2.5V情景：检测失败',xlabel='时间 ms',ylabel='电压 V')
    ax=axes[1,1];d=traces['button'];ax.plot([t*1000 for t in d['time']],d['v(node)'],color='#405e9b')
    ax.axhline(2.475,color='#888',ls='--');ax.set(title='BOOT按钮：理想开关/1ms RC',xlabel='时间 ms',ylabel='GPIO0 V')
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle('语音对讲V2 仿真审查 — 未通过整机验收，禁止据此下单生产',fontsize=16)
    fig.savefig(OUT/'waveforms.png',dpi=160)
    fig.savefig(OUT/'waveforms.svg')
    plot_svg=OUT/'waveforms.svg'
    plot_svg.write_text('\n'.join(line.rstrip() for line in plot_svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
    plt.close(fig)
except ImportError:
    print('matplotlib missing; numerical report/decks completed, plot not generated',file=sys.stderr)

print(json.dumps({'interface_checks':len(checks),'interface_pass':report['sections']['interfaces']['pass'],
    'adc_cases':len(adc),'adc_envelope_pass':report['sections']['battery_adc']['pass_within_generic_on_envelope'],
    'detector_failed_cases':sum(not c['recognizes_presence'] for c in detect),'ti_model':buck['status'],
    'whole_product_pass':False},ensure_ascii=False))
