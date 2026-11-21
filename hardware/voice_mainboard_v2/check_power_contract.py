"""Report the input power budget and model coverage without inventing rail results."""
from pathlib import Path
import hashlib
import json
import math
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
design = json.loads((ROOT / 'design.json').read_text(encoding='utf-8'))
contract = design['input_power']
sim = json.loads((ROOT / 'exports/function-simulation/results.json').read_text(encoding='utf-8'))
netfile = ROOT / 'exports/voice_mainboard_v2.net.xml'
xml = ET.parse(netfile).getroot()
nets = {node.attrib['ref'] + ':' + node.attrib['pin']: net.attrib['name'].removeprefix('/')
        for net in xml.findall('./nets/net') for node in net.findall('node')}
assert nets['J1:1'] == nets['J2:1'] == 'VIN_DC'
assert nets['JP1:1'] == 'POWER_REG_5V' and nets['JP1:2'] == 'SYS_5V'
assert nets['JP1:3'] == nets['J21:1'] == 'BENCH_REG_5V'

# Example load/efficiency scenarios, never measurements or component guarantees.
cases = []
for vin in [4.5, 5.0, 5.5]:
    for modem_a in [0.3, 2.0]:
        for other_5v_a in [0.3, 0.6, 0.9, 1.2]:
            regulator_efficiency = 0.85
            modem_buck_efficiency = 0.90
            load_w = 5.0 * other_5v_a + 3.8 * modem_a / modem_buck_efficiency
            input_a = load_w / (vin * regulator_efficiency)
            path_r = 0.06
            # Solve P = I * (Vin - I*R) / converter losses, low-current root.
            path_input_a = (vin-math.sqrt(vin*vin-4*path_r*load_w/regulator_efficiency))/(2*path_r)
            cases.append(dict(input_v=vin, modem_vbat_current_A=modem_a,
                other_system_5v_current_A=other_5v_a,
                assumed_5v_converter_efficiency=regulator_efficiency,
                assumed_modem_buck_efficiency=modem_buck_efficiency,
                input_current_A=input_a, within_3A=input_a <= 3.0,
                margin_to_3A_A=3.0-input_a,
                assumed_input_path_ohm=path_r, input_current_with_path_A=path_input_a,
                input_current_with_path_within_3A=path_input_a<=3.0,
                converter_input_after_path_V=vin-path_input_a*path_r,
                includes_battery_charging=False))

detector = sim['sections']['external_power_detector']
power = sim['sections']['modem_power']
adc = sim['sections']['battery_adc']
nodes = [
    dict(net='VIN_DC', location='J1.1 / J2.1', target='4.5–5.5V，标称5V',
         evidence='用户输入规格；完整输入保护/压降尚未验证', simulated_voltage=None),
    dict(net='POWER_REG_5V', location='J3.1 / JP1.1', target='稳压5V',
         evidence='电源板接口预留；升降压/UPS尚未定型', simulated_voltage=None),
    dict(net='SYS_5V', location='JP1.2 / J15.1', target='5V；负载下及瞬态验收4.75–5.25V',
         evidence='验收目标；当前没有闭环稳压仿真或实测结果', simulated_voltage=None),
    dict(net='MODEM_3V8', location='J19.2 / U1.42,43 / TP1', target='典型3.8V；模组要求3.4–4.5V',
         evidence='原候选反馈静态计算；3组理想源RC负载测试，降压闭环未通过验证',
         simulated_voltage={'ideal_source_rc_minimum_v':[c['min_v'] for c in power['rc_cases']],
                            'hypothetical_path_ohm':[c['resistance_ohm'] for c in power['rc_cases']]}),
    dict(net='ESP_3V3', location='J13.3 / J14.1', target='3.3V',
         evidence='现有开发板供电；确切LDO型号与电源顺序尚未核对', simulated_voltage=None),
    dict(net='MODEM_1V8', location='U1.24 / U3.6', target='模组VDD_EXT标称1.8V',
         evidence='模组输出规格；没有模组完整上电模型', simulated_voltage=None),
    dict(net='ADC_BAT_IO2', location='R17.2 / J13.17', target='4.2V电池时理想分压1.68V',
         evidence='通用MOS/RC模型27组；尚不包含ESP ADC误差',
         simulated_voltage={'minimum_60ms_v':min(c['adc_at_60ms_v'] for c in adc['cases'] if c['battery_v']==4.2),
                            'maximum_60ms_v':max(c['adc_at_60ms_v'] for c in adc['cases'] if c['battery_v']==4.2)}),
    dict(net='EXT_DETECT_GATE', location='R19.2 / Q5.1', target='4.5–5.5V输入经10k/100k分压',
         evidence='27组通用模型；实际温度、缓降及插拔未验证',
         simulated_voltage={'minimum_present_v':min(c['gate_present_v'] for c in detector['cases']),
                            'maximum_present_v':max(c['gate_present_v'] for c in detector['cases'])}),
    dict(net='MODEM_PWRKEY_N / MODEM_RESET_N', location='U1.7 / U1.15', target='开漏拉低≤0.5V并满足厂家时序',
         evidence='假定内部上拉的MOS模型；控制固件和模组实际启动未验证',
         simulated_voltage={'maximum_asserted_v':max(c['maximum_tested_window_v'] for c in sim['sections']['modem_control']['cases'])}),
]
report = dict(input_contract=contract, netlist_sha256=hashlib.sha256(netfile.read_bytes()).hexdigest(),
    topology='J1 raw input -> J2 regulated power board -> J3 regulated return -> JP1 -> SYS_5V -> modem buck and other loads',
    raw_bypass_absent=True, current_rating_is_not_output_capability=True,
    input_path_resistance_scenario_ohm=0.06,
    input_path_drop_at_3A_V=3*0.06, input_path_heat_at_3A_W=3*3*0.06,
    converter_minimum_input_after_path_scenario_V=4.5-3*0.06,
    resistance_is_not_measured=True, nodes=nodes, example_load_cases=cases,
    wide_input_operation_verified=False, full_product_simulated=False)
(ROOT/'exports/power-contract.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

lines = ['# 4.5～5.5V宽压输入与各路电压审查', '',
    '输入要求：J1圆口5.5mm外径/2.5mm内径、中心正极，接口处4.5～5.5V、标称5V；圆口、连接器与输入供电路径以3A为设计目标。不是要求电源永远精确输出5.000V。', '',
    '**当前完成输入契约、危险旁路移除、静态网表检查、检测电路情景和负载预算；整机宽压工作尚未验证，PCB不能发厂。**', '',
    '## 电源连接', '',
    'J1 → VIN_DC → J2 → 待确定的稳压/UPS电源板 → J3 POWER_REG_5V → JP1 → SYS_5V。系统5V再供ESP32、功放、可选雷达，并降压给裸ML307供电。输入低于5V时需要升压，高于5V时需要降压；仅升压且直通输入的UPS板不能自动满足此契约。具体UPS芯片仍按用户约定后续提供。', '',
    'JP1改为三针稳压电源选择：仅一个跳帽，1–2选择J3稳压电源，2–3选择J21独立稳压台架5V；无跳帽断开系统电源。J21不能接原始4.5～5.5V。台架供电只验证下游电路，不代表圆口宽压已通过。', '',
    'SYS_5V验收目标为负载及瞬态4.75～5.25V。裸ML307主供电为3.8V，不能直接接5V；USB检测端上限5.25V，原始输入不能直接送去。开发板、雷达具体供电容差仍需核对实际型号。', '',
    '## 输入电流预算', '',
    '3A输入不等于5V输出3A。以下使用假设的5V稳压效率85%、模组降压效率90%，并假设模组3.8V端峰值2A。其它5V负载包含ESP32、功放和雷达；这是情景核算，实际峰值和效率未测，不包含备用电池充电电流。两种路径结果分别为理想连接和假定60mΩ输入路径，不含适配器上游线缆压降。', '',
    '| 输入电压 | 其它5V负载 | 理想路径输入电流 | 60mΩ路径输入电流 | 60mΩ时相对3A |',
    '| --- | --- | --- | --- | --- |']
for case in cases:
    if case['modem_vbat_current_A']==2.0:
        margin = 3.0-case['input_current_with_path_A']
        lines.append(f"| {case['input_v']:.1f}V | {case['other_system_5v_current_A']:.1f}A | {case['input_current_A']:.3f}A | {case['input_current_with_path_A']:.3f}A | {'余量'+format(margin,'.3f')+'A' if margin>=0 else '超出'+format(-margin,'.3f')+'A'} |")
lines += ['', '在4.5V低端、模组2A峰值且其它5V负载0.6A的情景下，理想连接输入约2.992A，几乎没有余量；计入假设60mΩ路径后也会超出3A。需要实测总峰值、选择效率和电流能力合适的方案，并限制充电与峰值叠加；不能凭3A插座保证大音量、4G峰值及雷达一起工作。', '',
    '若输入连接器、保护器件及铜线合计电阻为60mΩ，3A时掉压0.18V、耗散0.54W，4.5V输入到稳压器只剩4.32V。这是阻抗情景，不是实测值；稳压器最低输入必须留出保护和连接压降。输入保护、实际连接器额定值、热设计与布线还未冻结。', '',
    '## 节点目标与已得到的结果', '',
    '| 节点/测量位置 | 目标 | 当前证据 |', '| --- | --- | --- |']
for node in nodes:
    result = '' if node['simulated_voltage'] is None else '；模型数值见JSON'
    lines.append(f"| {node['net']}（{node['location']}） | {node['target']} | {node['evidence']}{result} |")
lines += ['', f"外部输入检测27组情景覆盖4.5/5.0/5.5V，门极稳态计算范围{min(c['gate_present_v'] for c in detector['cases']):.3f}～{max(c['gate_present_v'] for c in detector['cases']):.3f}V；通用模型检测结果{'通过' if detector['pass_within_generic_envelope'] else '失败'}。这些结果不能验证5V稳压器、UPS或整机宽压。", '',
    '## 宽压验收仍需完成', '',
    '确定可采购的升降压/UPS与模组降压器件，核对启动、环路、有效电容、输入保护、倒灌、充电优先级和温升；完成布线后，在4.5/5.0/5.5V下分别验证冷启动、4G入网、最大音量通话、雷达接入、负载突变和掉电切换，记录各路示波器波形。', '',
    '数值与模型范围：[power-contract.json](exports/power-contract.json)。静态网表与PCB检查：[validation.json](exports/validation.json)。']
(ROOT/'宽压供电审查.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(json.dumps({'input_range_v':contract['range_at_connector_v'], 'raw_bypass_absent':True,
                  'budget_cases':len(cases), 'wide_input_verified':False}))
