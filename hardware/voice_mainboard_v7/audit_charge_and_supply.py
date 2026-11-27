"""Read current CAD/firmware and simulate only passive/control subcircuits.

No charging IC, switching-converter, battery electrochemistry or full-board
manufacturer macro-model is supplied here. Never label this a full UPS test.
"""
import hashlib,itertools,json,math,re,sys
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
sys.path.insert(0,str(ROOT.parent/'voice_mainboard_v2'))
from spice_runtime import run
OUT=ROOT/'exports/charge-supply-audit';OUT.mkdir(parents=True,exist_ok=True)
FILE=ROOT/'voice_mainboard_v7.kicad_pcb'
b=p.LoadBoard(str(FILE))
parts={fp.GetReference():fp for fp in b.GetFootprints()}
def pins(ref):return {pd.GetNumber():pd.GetNetname()for pd in parts[ref].Pads()if pd.GetNumber()}
def resistor(ref):
    match=re.match(r'([0-9.]+)([kM]?)(?:\s|$)',parts[ref].GetValue());assert match,ref
    return float(match[1])*{'':1,'k':1000,'M':1000000}[match[2]]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
expected={'U16':{'1':'BAT_TEMP','2':'CHG_PROG','3':'GND','4':'VIN_PROTECTED','5':'BAT_SENSE_IN','6':'CHG_FULL_N','7':'CHG_ACTIVE_N','8':'CHG_CE','9':'GND'},
          'U18':{'1':'GND','2':'SYS_5V','3':'VIN_PROTECTED','4':'UPS_PR1','5':'VIN_PROTECTED','6':'BAT_BOOST_5V','7':'SYS_5V','8':'SUPPLY_BAT_N47'},
          'U17':{'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NEG','4':'GND','5':'GND'},
          'Q7':{'1':'CHG_DISABLE_IO38','2':'GND','3':'CHG_CE'},
          'J23':{'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NTC'}}
for ref,pn in expected.items():assert pins(ref)==pn,(ref,pins(ref))
rt,rb=resistor('R65'),resistor('R66')
def rntc(temp):return 10000*math.exp(3950*(1/(temp+273.15)-1/298.15))
def threshold(ratio,top=rt,bottom=rb,r25=10000,beta=3950):
    parallel=top*ratio/(1-ratio)
    assert bottom>parallel
    ntc=1/(1/parallel-1/bottom)
    return 1/(1/298.15+math.log(ntc/r25)/beta)-273.15
nominal={'cold_C':threshold(.8),'hot_C':threshold(.45)}
corners={'cold_C':[],'hot_C':[]}
for s in itertools.product([-1,1],repeat=4):
    for ratio,key in [(.8,'cold_C'),(.45,'hot_C')]:
        corners[key].append(threshold(ratio,rt*(1+.01*s[0]),rb*(1+.01*s[1]),10000*(1+.01*s[2]),3950*(1+.01*s[3])))
case_results=[]
for name,ntc,cell_present in [('cell_25C',rntc(25),True),('cell_minus5C',rntc(-5),True),('cell_45C',rntc(45),True),('no_cell_no_NTC',1e15,False)]:
    # R67 links pack NTC to TEMP. CELL_NEG is ideal ground ONLY in this
    # control model when protection FETs conduct; actual offset not modeled.
    lines=['Vext ext 0 5','Vgpio pause 0 PWL(0 0 .004 0 .004001 3.3 .008 3.3 .008001 0 .012 0)',
           f'R68 ext ce {resistor("R68")}',f'R69 pause 0 {resistor("R69")}',
           'S_Q7 ce 0 pause 0 Q7_IDEAL','.model Q7_IDEAL SW(Ron=2 Roff=1e12 Vt=1.2 Vh=0)',
           f'R65 ext temp {rt}',f'R66 temp 0 {rb}',f'RpackNTC temp 0 {ntc}',
           f'R70 ext pr {resistor("R70")}',f'R71 pr 0 {resistor("R71")}']
    signals=['v(ce)','v(temp)','v(pr)']
    if cell_present:
        lines+=['Vcell battery 0 3.95',f'R17 battery adc {resistor("R17")}',f'R18 adc 0 {resistor("R18")}', 'Cadc adc 0 100n']
        signals.append('v(adc)')
    lines.append('.tran 2u .012')
    s,_=run('v7_'+name,lines,signals,OUT)
    def at(key,time):return s[key][min(range(len(s['time'])),key=lambda i:abs(s['time'][i]-time))]
    ratio=at('v(temp)',.003)/5
    case={'scenario':name,'cell_present_in_case':cell_present,'TEMP_over_VCC':ratio,'TEMP_allows_charge':.45<=ratio<=.8,'CE_GPIO_low_v':at('v(ce)',.003),'CE_GPIO_high_v':at('v(ce)',.006),'PR_at_external_5V_v':at('v(pr)',.003),'ADC_at_cell_3v95_v':at('v(adc)',.01)if cell_present else None,'model_completed':True}
    assert case['CE_GPIO_low_v']>4.9 and case['CE_GPIO_high_v']<.01
    assert abs(case['PR_at_external_5V_v']-5*resistor('R71')/(resistor('R70')+resistor('R71')))<1e-6
    if not cell_present:assert not case['TEMP_allows_charge']
    case_results.append(case)

fw=(REPO/'main/power_monitor.cpp').read_text(encoding='utf-8')
logic=(REPO/'main/power_monitor_logic.h').read_text(encoding='utf-8')
kconfig=(REPO/'main/Kconfig.projbuild').read_text(encoding='utf-8')
buildcfg=json.loads((REPO/'build/config/sdkconfig.json').read_text(encoding='utf-8'))
assert 'bool paused = webrtc_get_call_state() != CALL_STATE_IDLE || ota_is_in_progress();'in fw
report={'date':'2026-11-24','product':'语音对讲主板V7','PCB_sha256':sha(FILE),'firmware_sha256':sha(REPO/'main/power_monitor.cpp'),'logic_sha256':sha(REPO/'main/power_monitor_logic.h'),
 'scope':'Actual ngspice run of resistor dividers and an IDEAL Q7 switch. DC/manual topology audit using current PCB pad nets. NO full-board or full UPS simulation.',
 'complete_board_simulated':False,'battery_charge_discharge_qualified':False,'2A_qualified':False,'firmware_modified':False,'pcb_modified':False,
 'current_firmware':{'monitor_in_last_local_build':buildcfg.get('VOICE_POWER_MONITOR_ENABLE'),'Kconfig_default':False,'automatic_80_70_control_implemented':False,'pause_policy':'Call/ringing/OTA only; not linked to battery percent. GPIO38 high disables CE through Q7.','boot_and_firmware_absent_hardware_default':'R69 holds Q7 gate low; R68 pulls CE high. Charger itself uses normal 4.2V regulation subject to TEMP and other protections.','battery_absence_detected_reliably':False,'battery_absence_note':'ADC alone cannot prove cell presence; unloaded BAT output/capacitors may have voltage. No valid battery percentage should be inferred without presence qualification.'},
 'charger':{'model':parts['U16'].GetValue(),'RPROG_ohm':resistor('R64'),'nominal_current_ma':1200/resistor('R64')*1000,'nominal_end_current_ma':1200/resistor('R64')*100,'CV_nominal_v':4.2,'CV_datasheet_min_max_v':[4.158,4.242],'protection_overcharge_min_typ_max_v':[4.25,4.3,4.35],'cell_required':'Single-cell 4.2V rechargeable Li-ion/Li-polymer; cell charge-current and temperature limits must be matched. Not LiFePO4 or a 4.35V charging design.','80_percent_is_primary_overcharge_protection':False},
 'NTC':{'top_ohm':rt,'bottom_ohm':rb,'pack_assumed':'10k B3950, referenced CELL_NEG; actual pack unknown','nominal_charge_temperature_window':nominal,'corners_1pct_R_R25_B_no_IC_threshold_tolerance':{k:[min(v),max(v)]for k,v in corners.items()},'low_temperature_problem':True,'required_action':'Recalculate resistor network for selected cell, conservatively inside its permitted charging-temperature range. Current nominal low threshold is below 0C.','open_pack_NTC_TEMP_over_VCC':rb/(rt+rb),'open_pack_NTC_charge_inhibited_in_model':rb/(rt+rb)>.8,'short_NTC_note':'TP4056-MS datasheet says TEMP tied to GND disables temperature monitoring. Do not claim an NTC short is automatically protected.'},
 'no_battery':{'external_only_topology_supported':True,'path':'J1 -> F1/Q6 -> VIN_PROTECTED -> U18 VIN1 -> SYS_5V -> U2 modem rail / U13 ESP rail; amp supplied SYS_5V. No battery in this series path.','at_5V_PR_nominal':5*resistor('R71')/(resistor('R70')+resistor('R71')),'PR_reference_max':1.08,'no_NTC_EXPECTED_behavior':'TEMP remains above 80%VCC; charger suspended, independent external system path remains.','prototype_test_completed':False,'verification_needed':'Cold power-on with battery/NTC unplugged; loaded 4G attach/call/amp, disconnect/reconnect input, brownout and no spurious low-cell shutdown.'},
 'desired_80_70_policy':{'implemented':False,'additional_mainboard_chips_needed':False,'actuator':'Existing GPIO38 -> Q7 -> TP4056 CE','stop_percent_estimate':80,'resume_percent_estimate':70,'existing_table_80pct_mv':3950,'existing_table_70pct_mv_approx':3867,'thresholds_calibrated_for_actual_cell':False,'requirements':['Latch pause between lower/upper thresholds','Filtering, hysteresis and charging/load-voltage correction; short relaxed measurement before resume','Pause charging when ADC calibration/sample invalid','Treat no battery as external-only, not empty/full battery','Retain hardware voltage/overcurrent/temperature protection independent of ESP','Boot fallback and reboot persistence; enforce policy before charger startup if a strict 80% cap is required'],'reason':'Avoid prolonged high SOC for a standby backup cell; voltage-based percentage is approximate and not battery safety qualification.'},
 'ngspice_control_cases':case_results,
 'sources':{'charger':'build/ups-bom-20261124/TP4056-MS-C7473158.txt pages4/6/8','mux':'build/power-selection-20261119/tps2117.txt pages3/6/10/11','protection':'build/ups-bom-20261124/XB7608AJL.txt page3','CAD':'voice_mainboard_v7.kicad_pcb','firmware':'../../main/power_monitor.cpp'}}
(OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines=['# 语音对讲主板V7：充放电与无电池供电核查','',f'2026-11-24；PCB SHA256 `{report["PCB_sha256"]}`。本次只读核查，没有修改PCB、固件或刷机。','',
 '**结论：当前V7未完成整板电气仿真、锂电池完整充放电或2A实板资格测试；不能宣布全部正常。当前未实现80%停充/70%再充。外电独立供电拓扑支持不装电池使用，尚未在新板实测。**','',
 '## 实际已经运行的检查','',
 '- 核对当前PCB中U16充电、U17保护、U18电源切换、Q7充电暂停、电池J23引脚网络，与既有控制代码核对。',
 '- 本次ngspice运行4组被动/控制网络：25℃、−5℃、45℃、电池及NTC均不接。电阻来自当前PCB，Q7为理想开关。只验证TEMP分压、CE逻辑、PR分压与ADC分压。',
 '- 没有模拟电芯化学充放电、充电IC内部控制/动态、升降压开关/负载响应、PCB寄生或温升。这些运行完成不代表UPS或整板通过。','',
 '## 当前充电行为','',
 '- TP4056-MS按约4.2V恒流/恒压工作，R64=4kΩ名义300mA，电流降至约30mA时终止；后台充电管理没有80/70电量迟滞。',
 '- 电源监测默认关闭，最后本地构建记录也为关闭。源代码只在呼叫/通话/OTA暂停充电，空闲不以电量限制充电。',
 '- 4.2V充电器与约4.3V的过充保护各自工作，80%限制是减少长期高荷电状态的寿命策略，不能替代电芯规格、温度和电流保护。',
 f'- 当前假设10k/B3950 NTC，温度门限约{nominal["cold_C"]:.2f}～{nominal["hot_C"]:.2f}℃。−5℃在现分压模型中仍允许充电，必须先改温度窗口。NTC短到地会触发芯片温度监测禁用，不能声称短路自动停充。',
 '- 电池必须匹配4.2V单节锂离子/锂聚合物及300mA充电能力；小电池不能未经规格核对直接采用该电流。','',
 '## 80/70策略的落地条件','',
 '已有GPIO38经Q7控制CE，无需另外增加主板充电控制芯片。可用80%停充、70%再充的锁存策略，中间维持原状态。现电压估算表的对应值约3.95V/3.87V，只是未校准参考；充电电压抬升、负载压降与温度会影响结果，需要暂停充电后测量、滤波、持续确认和实芯校准。不得把瞬时ADC读数当作真实SOC。','',
 '启动、ADC异常及无电池状态应单独处理。当前硬件在ESP未控制时默认正常充电至4.2V；若希望严格限制启动/重启期间也不超过目标，需要修改默认CE控制及启动顺序。当前未实施这一策略。','',
 '## 不装电池只插电','',
 '设计供电路径为J1→保险丝/反接保护→TPS2117外电通路→系统5V→4G和ESP各自降压，功放取系统5V；电池不串在外电供电路径上。电池与NTC都不接时TEMP约为0.89×VCC，按规格暂停充电，系统仍可由外电供电。','',
 '不要短接NTC到地来关闭温度检测。电池ADC在没有电芯时也可能读到输出电容电压，因此电量软件需明确“未安装/未知”，不能将其当作电池充满或低电量关机。新板须验证无电池冷启动、4G入网/通话、扬声器负载、外电插拔和无误报关机。','',
 '[完整机器记录](results.json) · [PCB现版连接检查](../back-cleanup-validation.json)']
(OUT/'充放电核查.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items()if k in ['scope','complete_board_simulated','battery_charge_discharge_qualified','current_firmware','charger','NTC','ngspice_control_cases']},ensure_ascii=False,indent=2))
