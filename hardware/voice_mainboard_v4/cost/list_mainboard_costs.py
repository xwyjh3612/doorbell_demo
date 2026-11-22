"""List every cost line in the conditional 5-yuan UPS budget, not the active BOM."""
import json
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parent
baseline = json.loads((ROOT / "bom-budget.json").read_text(encoding="utf-8"))
budget = json.loads((ROOT / "ups5-budget.json").read_text(encoding="utf-8"))
research = json.loads((ROOT / "低价替代料核查.json").read_text(encoding="utf-8"))
removed = {ref for block in budget["removed_blocks"] for ref in block["refs"]}
removed |= {"D2", "D3", "D4"}
parts = {p["ref"]: dict(p, unit_cny=D(str(p["unit_cny"]))) for p in baseline["parts"] if p["populated"] and p["ref"] not in removed}
replacement_refs = {"sim_socket": "J10", "sim_esd_array": "D1", "esp_buck": "U13", "modem_buck_conditional": "U2"}
for candidate in research["candidates"]:
    if candidate["role"] in replacement_refs:
        ref = replacement_refs[candidate["role"]]
        parts[ref].update(value=candidate["model"], unit_cny=D(str(candidate["public_unit_cny"])), budget_basis="公开阶梯价候选，未完成板级验收")
parts["U14"]["value"] = "MAX98357A I2S功放（沿用目标预算）"
parts["UPS_BUDGET"] = {"value": "5V充放电、自动切换、欠压隔离、升压及配套，芯片待定", "unit_cny": D("5"), "budget_basis": "用户指定整组预算"}

groups = [
    ("ESP32-S3模组", ["U7"]),
    ("ML307C-DL模组", ["U1"]),
    ("5V供电与UPS整组", ["UPS_BUDGET"]),
    ("5.5/2.5mm圆口", ["J1"]),
    ("输入保险丝、反接保护及电阻", ["F1", "Q6", "R32"]),
    ("4G降压芯片，条件低价候选", ["U2"]),
    ("4G降压电感、电容、反馈及配套", ["R1", "C3", "C4", "C5", "L1", "C6", "C7", "R2", "R3", "C37"]),
    ("ESP 3.3V降压芯片，低价候选", ["U13"]),
    ("ESP降压电感、电容与反馈电阻", ["L4", "C59", "C60", "R59", "R60"]),
    ("I2S功放芯片", ["U14"]),
    ("功放去耦及配置阻容", ["R61", "R62", "C61", "C62"]),
    ("喇叭插座", ["J15"]),
    ("外接麦克风插座与去耦", ["J14", "C26"]),
    ("4G 470μF储能电容", ["C8"]),
    ("4G其余去耦及滤波电容", ["C10", "C11", "C12", "C13", "C14", "C15", "C16", "C17", "C18", "C19"]),
    ("UART/DTR电平转换芯片，3颗", ["U3", "U4", "U5"]),
    ("4G开机、复位控制及按键", ["R4", "R5", "Q1", "R6", "Q2", "R8", "SW3"]),
    ("nano SIM座，低价候选", ["J10"]),
    ("四路SIM静电保护阵列，1颗", ["D1"]),
    ("SIM串联电阻及去耦", ["R9", "R10", "R11", "R12", "C20"]),
    ("LTE天线座与0Ω连接", ["J11", "R13"]),
    ("USB维修路线0Ω选装连接", ["R26", "R27", "R30"]),
    ("ESP去耦、EN及BOOT配套阻容", ["R57", "C56", "C57", "C58", "R14"]),
    ("ESP BOOT呼叫键与复位键，2颗", ["SW1", "SW2"]),
    ("TTL四针排针", ["J18"]),
    ("外部呼叫按钮插座", ["J17"]),
    ("可选雷达四针接口", ["J16"]),
    ("ESP电池电压采样及开关电路", ["Q3", "Q4", "R15", "R16", "R17", "R18", "C28"]),
    ("外部电源掉电检测电路", ["Q5", "R19", "R20", "R21", "C29"]),
]
accounted = [ref for _, refs in groups for ref in refs]
assert len(accounted) == len(set(accounted))
assert set(accounted) == set(parts), (set(parts) - set(accounted), set(accounted) - set(parts))
total = sum((p["unit_cny"] for p in parts.values()), D(0))
assert total == D(str(budget["scenarios"]["conditional_cheaper_modem_buck"]["material_per_board_cny"]))
fees = budget["manufacturing_allowances_per_board_cny"]
fee_total = sum((D(str(v)) for v in fees.values()), D(0))

lines = [
    "# 当前主板费用逐项清单：1000台预算",
    "",
    "日期：2026-11-22。沿用5V供电＋UPS材料5元、ML307C-DL 10元、ESP32-S3 N8R8 12元的用户预算。本表主列为条件低价4G降压方案：材料42.40246元，含PCB/加工/损耗/测试50.90246元。保留原4G降压则材料44.78531元、主板53.28531元。",
    "",
    "这是一份尚未落到原生PCB的降本费用清单。原板位号用于对照，尤其D1这一预算行代表新的一颗四路阵列，并非在原D1封装上换芯片。UPS芯片未识别，无法列出其内部逐颗物料；5元仅作为整组预算。",
    "",
    "## 材料分项",
    "",
    "| 部分 | 含哪些零件/原板对照位号 | 每台材料/元 | 1000台/元 |",
    "|---|---|---:|---:|",
]
for label, refs in groups:
    amount = sum((parts[r]["unit_cny"] for r in refs), D(0))
    lines.append(f"| {label} | {', '.join(refs)} | {amount:.5f} | {amount * 1000:.2f} |")
lines += [
    f"| **板上材料合计** | **全部分项相加，无重复位号** | **{total:.5f}** | **{total * 1000:.2f}** |",
    "",
    "## 制造费用",
    "",
    "| 费用 | 每台/元 | 1000台/元 |",
    "|---|---:|---:|",
    f"| 100×75mm双层PCB | {fees['bare_PCB']:.2f} | {fees['bare_PCB'] * 1000:.2f} |",
    f"| SMT贴片、插件加工 | {fees['SMT_THT']:.2f} | {fees['SMT_THT'] * 1000:.2f} |",
    f"| 物料损耗、烧录与功能测试 | {fees['loss_programming_test']:.2f} | {fees['loss_programming_test'] * 1000:.2f} |",
    f"| **制造费用合计** | **{fee_total:.2f}** | **{fee_total * 1000:.2f}** |",
    f"| **材料＋制造总计** | **{total + fee_total:.5f}** | **{(total + fee_total) * 1000:.2f}** |",
    "",
    "## 逐颗材料对照",
    "",
    "每个列出的原板位号按1颗/台计价；UPS_BUDGET为1组/台。模型与价格是预算情景，不构成可直接下单的已批准BOM。所有配套阻容逐颗列入，没有额外的隐含‘小零件费’。",
    "",
    "| 原板对照位号/预算组 | 型号或参数 | 数量/台 | 单颗或整组预算/元 |",
    "|---|---|---:|---:|",
]
for _, refs in groups:
    for ref in refs:
        p = parts[ref]
        lines.append(f"| {ref} | {p['value']} | 1 | {p['unit_cny']:.5f} |")
lines += [
    "",
    "## 预算边界",
    "",
    "- UPS的5元假设覆盖充电、欠压/隔离、自动切换、统一5V升压及配套阻容和电池/NTC连接器；电池与NTC本体不含。圆口/输入保护、ESP/4G降压、功放及ESP ADC仍另计。若5元实际已经包含圆口/输入保护，再扣1.294元，条件方案主板为49.60846元。",
    "- TPS563201最低输入4.5V，原外部输入4.5V再经过保护压降后不能保证工作；反馈、配套与控制需重设计验收。本表沿用旧降压配套预算，最终配套增减未定。SIM和ESP低价候选也尚未通过板级验收。",
    "- 模组10/12元和UPS5元为用户指定预算，功放3元等部分沿用未询价目标；新候选价来源见[低价替代料核查](低价替代料核查.md)。",
    "- PCB、加工和损耗/测试共8.5元是预算额度，尚无工厂正式报价；税运、最低包装、工程一次性费用及客供条件未确定。",
    "- 排除适配器、电池/NTC、外壳、喇叭、外接麦克风、雷达、线束；雷达接口保留，雷达模块不计。USB维修路线本表只计默认0Ω，未贴的USB连接器/Host选装料不计。",
    "",
    "精确情景总计与旧电路扣除记录见[ups5-budget.json](ups5-budget.json)，重新运行`list_mainboard_costs.py`可生成本清单。",
    "",
]
(ROOT / "当前主板全部费用.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Verified {len(groups)} material groups, {len(parts)} part/budget lines; material={total}, assembled={total + fee_total}")
for label, refs in groups:
    print(label, sum((parts[r]['unit_cny'] for r in refs), D(0)))
