"""Independent power pin checks and 5V/2A parallel-converter budget scenarios."""
from pathlib import Path
import json,math,hashlib
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
xmlfile=ROOT/'exports/voice_mainboard_v2.net.xml'
xml=ET.parse(xmlfile).getroot()
pins={(node.attrib['ref'],node.attrib['pin']):net.attrib['name'].removeprefix('/') for net in xml.findall('./nets/net') for node in net.findall('node')}
checks={('J1','1'):'VIN_DC',('F1','1'):'VIN_DC',('F1','2'):'VIN_FUSED',('Q6','3'):'VIN_FUSED',('Q6','2'):'VIN_PROTECTED',('J2','1'):'VIN_PROTECTED',('JP4','1'):'VIN_PROTECTED',('JP4','2'):'POWER_BUS',('JP4','3'):'POWER_REG_5V',('U2','3'):'POWER_BUS',('U6','2'):'POWER_BUS',('U6','9'):'BOARD_REG_5V',('J3','1'):'POWER_REG_5V',('JP1','1'):'BOARD_REG_5V',('JP1','2'):'SYS_5V',('JP1','3'):'BENCH_REG_5V',('J21','1'):'BENCH_REG_5V',('R2','1'):'BUCK_3V8',('R2','2'):'BUCK_FB',('J19','2'):'MODEM_3V8'}
assert all(pins[p]==n for p,n in checks.items()),'Power topology differs from independently reviewed pin table'
assert design['input_power']['input_path_design_current_A']==2
cases=[]
for vin in [4.5,5.0,5.5]:
 for modem in [.3,1.0,2.0]:
  for other in [.1,.2,.3,.4,.6]:
   watts=3.792*modem/.9+5*other/.9
   amps=(vin-math.sqrt(vin**2-4*.06*watts))/(2*.06)
   cases.append(dict(input_v=vin,modem_vbat_current_A=modem,other_5v_current_A=other,assumed_modem_efficiency=.9,assumed_system_efficiency=.9,assumed_input_path_ohm=.06,input_current_with_path_A=amps,within_2A_continuous_scenario=amps<=2,converter_input_v=vin-amps*.06,includes_battery_charging=False,measured=False))
report=dict(revision=design['revision'],input_contract=design['input_power'],adapter_baseline='5V/2A',topology='J1 -> F1/Q6 -> JP4 POWER_BUS; parallel U2 3.8V modem and U6 5V system; JP1 selects system or bench 5V',independent_pin_checks=len(checks),netlist_sha256=hashlib.sha256(xmlfile.read_bytes()).hexdigest(),no_mandatory_double_conversion_for_modem=True,example_load_cases=cases,current_is_at_adapter_not_modem=True,raw_5v_bypass_absent=True,wide_input_operation_verified=False,converter_loop_verified=False,full_product_simulated=False,includes_battery_charging=False)
(ROOT/'exports/power-contract.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines=['# 2A基准与并行供电审查','',
'当前基准为用户已测试的5V/2A适配器；输入范围保留4.5～5.5V，圆口为5.5mm外径/2.5mm内径、中心正极。3A不作为适配器必选要求。','',
'J1经过F1保险及Q6反接保护，JP4的1–2选择直供、2–3选择J3返回的未来UPS稳压输出。POWER_BUS并行供给U2模组降压和U6系统升降压。U2输出约3.792V，U6输出固定5V，ML307不加载U6，也不必先转换成5V再降到3.8V。','',
'JP1的1–2为板载5V，2–3为J21独立台架稳压5V；每个选择位仅一个跳帽。J19保持板载3.8V/外部3.8V选择，外部口不能接5V。UPS与电池尚未集成充放电；当前PCB具有插接接口，未指定未知芯片的安装尺寸。','',
'U2改为TPS62933P，原TPS563201已退出当前设计。它具有3.8V最低输入及低压差扩展导通功能；494µF混合输出电容的启动和环路仍须验证。U6候选为TPS63061固定5V，资料给出VIN>4V时5V升压输出1.3A；它负责ESP32、音频和雷达支路。芯片额定能力不能代替整机实测。','',
'下面假设两路效率均为90%、输入路径60mΩ，模组VBAT瞬时负载2A。数字不是现有样机的功耗测量，不含电池充电。','',
'| 圆口输入 | 其他5V负载 | 估算输入电流 | 相对2A连续能力 |','| --- | --- | --- | --- |']
for c in cases:
 if c['modem_vbat_current_A']==2 and c['other_5v_current_A'] in [.1,.2,.3,.4]:
  delta=2-c['input_current_with_path_A']
  lines.append(f"| {c['input_v']:.1f}V | {c['other_5v_current_A']:.1f}A | {c['input_current_with_path_A']:.3f}A | {'余量' if delta>=0 else '超过'} {abs(delta):.3f}A |")
lines+=['','2A适配器继续作为首板验证基准。低端4.5V与4G峰值同时发生时，留给其他支路的持续功率会减少；电容只能承担短暂峰值。实板要同时记录VBAT、5V及输入电流，测入网和最大音量通话，再确定可承诺的全负载范围。不能从单个ML307的2A峰值直接推出整机一定需要3A，也不能据此保证所有负载同时最大时仍低于2A。','','当前引脚核对通过，供电路径还没有完成环路、瞬态和热验证。工程文件继续标记为未放行。数字及来源见[power-contract.json](exports/power-contract.json)。','','资料：[TPS62933](https://www.ti.com/lit/ds/symlink/tps62933.pdf)、[TPS63060/61](https://www.ti.com/lit/ds/symlink/tps63060.pdf)。']
(ROOT/'宽压供电审查.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(revision=design['revision'],pin_checks=len(checks),budget_cases=len(cases),adapter='5V/2A',hardware_verified=False)))
