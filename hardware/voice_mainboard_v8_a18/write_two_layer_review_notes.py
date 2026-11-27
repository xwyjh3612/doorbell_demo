"""Write review notes from the exact current native reports and model results."""
from pathlib import Path
import datetime,hashlib,json,os

ROOT=Path(__file__).resolve().parent
FILE=Path(os.environ.get('A18_AUDIT_BOARD',str(ROOT/'two_layer_work/voice_mainboard_a18_2layer.kicad_pcb'))).resolve()
OUT=FILE.parent
review=json.loads((OUT/'exports/review-summary.json').read_text(encoding='utf-8'))
sha=hashlib.sha256(FILE.read_bytes()).hexdigest()
assert review['PCB_sha256']==sha
electrical=json.loads((OUT/'exports/electrical-audit/results.json').read_text(encoding='utf-8'))
copper=json.loads((OUT/'exports/copper-path-audit.json').read_text(encoding='utf-8'))
models=json.loads((OUT/'exports/model-inventory.json').read_text(encoding='utf-8'))
widths=json.loads((OUT/'exports/power-width-audit.json').read_text(encoding='utf-8'))
assert electrical['PCB_sha256']==copper['PCB_sha256']==models['PCB_sha256']==sha
assert widths['PCB_sha256']==sha
counts=review['native_DRC_counts']
storage_report=OUT/'exports/vbat-storage/results.json'
storage_note=''
if storage_report.exists():
    storage=json.loads(storage_report.read_text(encoding='utf-8'))
    assert storage['PCB_sha256']==sha
    cases={q['assumed_source_interruption_us']:q['minimum_VBAT_V'] for q in storage['cases'] if q['with_C75_C76']}
    storage_note=(f'按ML307C手册在VBAT保留C6/C7，并加C75/C76各220µF。另运行8组局部储能模型，'
        f'按源中断且负载需求升至2A模拟：装上新电容后，50µs最低{cases[50]:.3f}V，100µs最低{cases[100]:.3f}V。'
        '结果不覆盖稳压器启动、限流或环路稳定性；同版报告见[VBAT储能模型](exports/vbat-storage/results.json)。\n\n')
now=datetime.datetime.now().astimezone().isoformat()
rows=[]
for q in copper['paths']:
    if q['trace_graph_connected']:
        rows.append(f"| {q['net']} | {q['from']} → {q['to']} | {q['centreline_length_mm']:.2f} | {q['minimum_width_mm_on_estimated_path']} | {q['estimated_drop_at_2A_V']:.4f} |")
    else:
        rows.append(f"| {q['net']} | {q['from']} → {q['to']} | 显式铜线图未连通 | — | — |")
text=f'''# 语音对讲主板：A18两层设计审查

更新：{now}。**当前工作版尚未生产放行。** 本记录只对应下列PCB哈希，不能使用四层工程的报告替代它。

`{sha}`

## 当前保存版本的检查

| 项目 | 结果 |
| --- | ---: |
| 铜层 | 2 |
| ERC违规 | {review['ERC_violations']} |
| DRC违规（含悬空线等警告） | {counts['violations']} |
| 未连接项 | {counts['unconnected_items']} |
| 原理图一致性问题 | {counts['schematic_parity']} |
| 与原理图逐项比对的引脚网络分配 | {electrical['connected_pins_checked']} |

未连接项必须继续修复；没有删掉必要引脚、改变网络名称或添加DRC排除项来凑通过数字。查看[正背面预览与模型结果](exports/preview.html)、[原生DRC报告](exports/review-drc.json)和[PCB工程](voice_mainboard_a18_2layer.kicad_pcb)。

## 本轮布局和布线

4G降压、电平转换与硬复位靠近模组；功放靠近ESP音频引脚。SIM的静电保护和串阻放在SIM座背面。两路降压的反馈元件靠近芯片，升压芯片朝向电感，开关线采用局部走法，避免绕过USB和音频区域。

优先布置较宽的供电主干，再补剩余信号。普通密集引脚过孔采用0.45mm焊环/0.20mm孔，较大的电源过孔和短引脚颈线单独核查。下面的数据从当前铜线与过孔图计算，含短颈线；表中的最小宽度不能当作整条主干宽度。

| 网络 | 起点 → 终点 | 路径mm | 最小线宽mm | 假设2A压降V |
| --- | --- | ---: | ---: | ---: |
'''+ '\n'.join(rows)+f'''

上述估算假设35µm铜厚、20µm孔铜、20℃，不含芯片、接点、电感、电池内阻、温升和并联地铜电流分配。开关节点的2A栏仅用于铜线比较，不代表电感峰值电流已经合格。不能用这些数字宣布整机已通过2A峰值测试。

当前电源线宽审查发现{sum(len(q['long_narrow_segments']) for q in widths['rails'])}段长度超过1.5mm且线宽小于0.5mm的铜线（含支路和悬空段）。这些线路需要结合实际电流路径继续调整，详见[电源线宽审查](exports/power-width-audit.json)。单段阈值不能替代连续短颈线和整条供电回路的检查。

## 机械与接口

A18外壳85×85×31mm；主板外包73×73mm，厚1.2mm，四个Ø3mm孔的孔距66×66mm；下方36mm缺口避让电池仓。中央呼叫键、RGB指示灯、可选生命体征接口、4针TTL和USB预留均保留。

现有模型可显示{models['with_existing_model']}个封装，{len(models['without_existing_model'])}个没有可用模型，详见[模型清单](exports/model-inventory.json)。ML307、SIM座和电源口等缺失模型不能据空白位置判断装壳无碰撞。螺柱外径、按钮与导光柱、具体电芯和接线弯折空间仍需实物或厂家图纸确认。

## 实际仿真范围与电池行为

运行12组ngspice被动储能模型和4组分压/理想充电控制模型，核对了实际负载激励、反馈电压容差和引脚网络。没有建立ESP32、ML307、开关电源芯片内部、电芯化学、蜂窝网络或整板热模型。ERC/DRC与这些局部模型不能代替新板限流上电和通话测试。

{storage_note}外电不经过电池串联路径，因此拓扑支持不安装电池只插电；需样板验证启动与负载瞬态。电池接口为BAT+、CELL_NEG、NTC；CELL_NEG不能短接系统GND，否则会绕过保护。

TP4056当前电阻设定为100mA，GPIO38具备暂停充电的电路分配。**80%停充/70%恢复的电量迟滞没有在固件中实现。** 当前按充电芯片的4.2V规则工作，不能用电压简单等同准确SOC。NTC暂按10k/B3950，具体电芯和温度元件尚未冻结。

## 打样前仍需闭环

- 所有未连接和原生DRC违规收敛到0；再次确认这版的网表与工程一致。
- 审核电源主干、短颈线、开关回路与回流路径；USB/射频阻抗及参考地需专门核查。
- L5型号及焊盘已核对，采购料号与备料需确认；L4供应量与关键自建封装需确认。
- 电芯的放电峰值、NTC及低电量切换条件、充电温升需实际样板验证。低电量下5V峰值2A可能使电芯电流超过4A。
- 核对真实外壳装配，再按限流上电、无电池启动、三路电压、4G入网与通话负载、断电切换、低电量/温度暂停顺序测试。

本轮CAD工作没有刷固件，也没有改动官方通信协议或音频主动丢旧包策略。
'''
(OUT/'设计审查记录.md').write_text(text,encoding='utf-8')
design=json.loads((OUT/'design.json').read_text(encoding='utf-8'))
design['status']='UNRELEASED TWO-LAYER ROUTING REVIEW'
design['manufacturing_ready']=False
design['last_native_review']={'generated_at':now,'PCB_sha256':sha,'counts':counts}
(OUT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
print('Updated exact two-layer review notes, with unresolved items retained.')
