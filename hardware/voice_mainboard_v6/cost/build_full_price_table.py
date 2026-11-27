"""Reconcile the current PCB BOM with saved public prices; never edit CAD."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs' / 'voice-mainboard-cost-20261124'
OUT.mkdir(parents=True, exist_ok=True)

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

bom = load(HERE.parent / 'exports/bom.json')['parts']
inputs = load(HERE / 'part-price-inputs.json')
old = load(HERE / '1000台预算.json')
parts = [p for p in bom if not p.get('dnp') and p.get('kind') == 'pcb']
assert len(parts) == 116
overrides = {r['ref']: r for r in old['public_price_overrides']}
public_rows = load(ROOT / 'hardware/voice_mainboard_v5/cost/jlc-100/public-part-prices.json')['rows']
public_by_ref = {ref: row for row in public_rows for ref in row['refs']}
observed = {r['sku']: r for r in load(ROOT / 'build/price-recheck-20261122/observed-pages.json')}
new_sources = {}

def from_search(ref, filename, expected_model):
    doc = load(ROOT / 'build/v6-price-recheck-20261124' / filename)
    record = next(r for r in doc['records'] if r['model'] == expected_model)
    assert record['stock'] >= 1000 and record['encapsulation'] == '0603'
    price = max((r for r in record['tiers'] if r['start'] <= 1000), key=lambda r: r['start'])['cny']
    new_sources[ref] = dict(unit=price, code=record['code'], model=record['model'], source=record['page'],
                            status='公开阶梯价；候选规格待确认', note='2026-11-24公开查询；仅补充成本候选，未修改BOM或PCB。', evidence=str((ROOT / 'build/v6-price-recheck-20261124' / filename).relative_to(ROOT)))

from_search('R62', 'RT0603BRD0710KL.json', 'RT0603BRD0710KL')
from_search('R63', '0603WAF3002T5E.json', '0603WAF3002T5E')
from_search('R65', '0603WAF6191T5E.json', '0603WAF6191T5E')
from_search('R70', 'RT0603BRD07100KL.json', 'RT0603BRD07100KL')

for ref, code in [('J23', 'C2937625'), ('C67', 'C15850'), ('C68', 'C15850'), ('C69', 'C1591'), ('C70', 'C1591')]:
    r = observed[code]
    new_sources[ref] = dict(unit=r['page_price'], code=code, model=r['name'], source=f"https://item.szlcsc.com/{r['id']}.html",
                           status='历史页面参考；阶梯未核', note='2026-11-22页面记录；采购阶梯未确认。' + ('10µF 25V X5R 0805候选；额定值高于原10V，仍需核查偏压容量。' if ref in ['C67','C68'] else ''), evidence='build/price-recheck-20261122/observed-pages.json')
for ref in ['C64','C65','C66','C71','C72','C73']:
    r = observed['C398815']
    new_sources[ref] = dict(unit=r['page_price'], code=r['sku'], model=r['name'], source=f"https://item.szlcsc.com/{r['id']}.html",
                           status='历史候选参考；规格待确认', note='原22µF 10V X5R 0805；参考22µF 16V 0805候选。介质、直流偏压有效容量及供货需确认，未换料。', evidence='build/price-recheck-20261122/observed-pages.json')

roles = {
    'J1':'圆口电源输入','F1':'输入自恢复保险丝','Q6':'输入反接保护','L1':'4G供电电感','U1':'4G模组',
    'U2':'4G供电降压','U3':'串口电平转换','U4':'串口电平转换','U5':'控制信号电平转换',
    'U7':'主控模组','U13':'3.3V降压','U14':'I2S功放','U15':'UPS升压','U16':'电池充电',
    'U17':'电池保护','U18':'外电/电池电源切换','U19':'供电状态检测','Q7':'充电控制',
    'J10':'SIM卡座','J11':'4G天线座','J14':'麦克风模块接口','J15':'喇叭接口','J16':'可选雷达接口',
    'J17':'外接呼叫按钮接口','J18':'TTL刷机接口','J23':'电池/NTC接口',
    'SW1':'复位按钮','SW2':'BOOT/接听按钮','SW3':'4G控制按钮',
    'L4':'3.3V降压电感','L5':'UPS升压电感','C8':'4G供电储能电容',
}
rows = []
for p in parts:
    ref = p['ref']
    pi = inputs[ref]
    budget = pi['unit_cny']
    basis = pi['basis']
    status = '采购预算；未核报价' if 'unquoted' in basis else '历史价格参考；阶梯未核'
    if 'user specified' in basis:
        status = '用户目标价；未取得订单报价'
    elif 'public1000 tier' in basis:
        status = '公开阶梯价记录'
    elif 'public candidate' in basis:
        status = '外部候选参考；非嘉立创报价'
    public = None
    public_status = '待核价'
    source = pi.get('source') or p.get('source', '')
    code = p.get('lcsc') or ''
    candidate_model = ''
    note = ''
    evidence = 'hardware/voice_mainboard_v6/cost/part-price-inputs.json'
    if ref in overrides:
        o = overrides[ref]
        public, source = o['public_reference'], o['source']
        public_status = '公开阶梯价记录（2026-11-23）'
        candidate_model = public_by_ref[ref]['mpn']
        code = public_by_ref[ref]['lcsc']
        evidence = 'hardware/voice_mainboard_v5/cost/jlc-100/public-part-prices.json'
        if ref in ['U3','U4','U5','Q1','Q2','Q4','Q5']:
            note = '阶梯按同一料号合并采购数量计算。'
    elif 'public1000 tier' in basis and source.startswith('https://item.szlcsc.com/'):
        public, public_status = budget, '公开阶梯价记录（2026-11-24）'
    if ref in new_sources:
        r = new_sources[ref]
        budget, public = r['unit'], r['unit']
        status = public_status = r['status']
        source, code, candidate_model, note, evidence = r['source'], r['code'], r['model'], r['note'], r['evidence']
    # Reuse saved same-footprint candidates for common parts. Keep the existing
    # budget intact so lower reference prices remain visible for comparison.
    common_code = None
    if public is None and p['footprint'].endswith('C_0603_1608Metric') and (p['value'].startswith('100n') or p.get('lcsc') == 'C1591'):
        common_code = 'C1591'
    elif public is None and p['footprint'].endswith('C_0805_2012Metric'):
        if p['value'].startswith('22u'):
            common_code = 'C398815'
        elif p['value'].startswith('10u'):
            common_code = 'C15850'
    elif public is None and p['footprint'].startswith('Connector_PinHeader_2.54mm:'):
        common_code = {'PinHeader_1x02_P2.54mm_Vertical':'C492401', 'PinHeader_1x04_P2.54mm_Vertical':'C2691448', 'PinHeader_1x05_P2.54mm_Vertical':'C492404'}.get(p['footprint'].split(':')[-1])
    if common_code:
        candidate = observed[common_code]
        public = candidate['page_price']
        public_status = '历史同封装候选参考；阶梯未核'
        code, candidate_model = common_code, candidate['name']
        source = f'https://item.szlcsc.com/{candidate["id"]}.html'
        evidence = 'build/price-recheck-20261122/observed-pages.json'
        note += ' 候选名义容量/接口针数与现有封装相符；耐压、介质、偏压容量或实物尺寸需核查，未改BOM。'
    if budget is None:
        budget = 0.1 if '0.1%' in p['value'] else 0.025
        status = '预算补位；实际单价待核'
        note = '仅用于全表规划：0.1%电阻暂按0.10元，其余电阻暂按0.025元；不代表嘉立创报价。'
    if ref == 'U7':
        note = '12元是用户目标；本版实际需要N8R8模组，Flash/PSRAM配置必须一致。'
    if ref == 'U1':
        note = '10元是用户目标；公开参考为ML307C-DL，尚未取得目标价采购报价。'
    if ref in ['L1','L4']:
        note += ' C83455历史库存不足批量；需有库存的兼容电感，不能凭单价直接换。'
    if ref == 'U2':
        public = None
        public_status = '非嘉立创来源；待核价'
        note = '原0.29263元来源链接为数据手册，不能证明嘉立创阶梯价。'
    if ref in ['SW1','SW2','SW3']:
        note = '0.18元仅预算；准确尺寸、焊盘匹配及现货料号待确认。'
    role = roles.get(ref, '电阻' if ref.startswith('R') else '电容' if ref.startswith('C') else '控制MOS管')
    rows.append(dict(ref=ref, role=role, model=p.get('mpn') or p['value'], spec=p['value'],
                     package=p['footprint'].split(':')[-1], quantity=1, budget_unit=budget, budget_status=status,
                     public_unit=public, public_status=public_status, code=code, candidate_model=candidate_model,
                     source=source, note=note, evidence=evidence, group=p['group']))

budget_total = sum(r['budget_unit'] for r in rows)
public_partial = sum(r['public_unit'] or 0 for r in rows)
public_missing = [r['ref'] for r in rows if r['public_unit'] is None]
mixed_material = sum(r['public_unit'] if r['public_unit'] is not None else r['budget_unit'] for r in rows)
fillers = [r for r in rows if r['budget_status'].startswith('预算补位')]
pcb = old['PCB_historical_public_batch_cny'] / 1000
smt = old['assembly_public_calculator_batch_cny'] / 1000
summary = dict(budget_material=budget_total, budget_filler=sum(r['budget_unit'] for r in fillers),
               budget_filler_count=len(fillers), public_material_partial=public_partial,
               public_missing_count=len(public_missing), public_missing_refs=public_missing,
               pcb_unit=pcb, assembly_unit=smt, budget_board=budget_total+pcb+smt,
               public_plus_budget_material=mixed_material, public_plus_budget_board=mixed_material+pcb+smt,
               public_partial_board=public_partial+pcb+smt)
data = dict(date='2026-11-24', quantity=1000, product='语音对讲主板V6', populated_count=len(rows),
            pcb_sha256=hashlib.sha256((HERE.parent/'voice_mainboard_v6.kicad_pcb').read_bytes()).hexdigest(),
            final_supplier_quote=False, manufacturing_ready=False, rows=rows, summary=summary,
            excluded_refs=[dict(ref=p['ref'],model=p['value'],reason='默认不装' if p.get('dnp') else p.get('kind','')) for p in bom if p not in parts],
            scope='仅主板元件、PCB、贴片与插件；不含电池/NTC、麦克风模块、喇叭、雷达、天线、外壳、适配器、运费、物料损耗和测试工装。')
(HERE/'整板逐项价格.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def price(v):
    return '待核价' if v is None else f'{v:.5f}'.rstrip('0').rstrip('.')

lines = ['# 语音对讲主板V6整板价格表', '', '核价日期：2026-11-24；计划1000台；100×75mm、两层板。默认装116个元件：109个贴片、7个插件。', '',
         '本表包含UPS在内的全部主板元件。左侧预算价保留用户ML307 10元、ESP32 12元目标；右侧仅显示有证据的公开/历史参考价。候选料并未修改电路板。', '',
         '| 费用 | 单台/元 | 1000台/元 | 价格边界 |','|---|---:|---:|---|',
         f'| 全表材料规划预算 | {budget_total:.4f} | {budget_total*1000:.2f} | 含用户目标价、历史预算与{len(fillers)}项预算补位 |',
         f'| PCB | {pcb:.4f} | {pcb*1000:.2f} | 2026-11-22同尺寸历史公开报价；非实际V6文件审单价 |',
         f'| 贴片及插件加工 | {smt:.4f} | {smt*1000:.2f} | 公开计算器，普通换料费用重建；最终料号合并、库别待审 |',
         f'| 主板规划预算合计 | {budget_total+pcb+smt:.4f} | {(budget_total+pcb+smt)*1000:.2f} | 不是已取得的嘉立创完整报价 |',
         f'| 公开参考有价项目小计 | {public_partial:.4f} | {public_partial*1000:.2f} | 仍有{len(public_missing)}个元件无公开参考价；禁止当作完整材料总价 |',
         f'| 公开有价项目＋其余预算＋PCB加工 | {mixed_material+pcb+smt:.4f} | {(mixed_material+pcb+smt)*1000:.2f} | 混合规划值；不能称为全嘉立创报价 |',
         '',f'预算补位共{len(fillers)}个电阻、{summary["budget_filler"]:.4f}元/台：'+ '、'.join(r['ref'] for r in fillers)+'。这一部分明确为估算，并非核得的真实单价。其余历史预算也需要实际下单核价。', '',
         '## 每个装配元件', '', '| 位号 | 用途 | 原型号/规格 | 封装 | 数量 | 预算单价/元 | 公开参考单价/元 | 预算依据 | 公开价格依据 | 候选料号 | 来源 |',
         '|---|---|---|---|---:|---:|---:|---|---|---|---|']
for r in rows:
    source = f'[页面]({r["source"]})' if r['source'] else '无报价链接'
    lines.append('| '+' | '.join([r['ref'],r['role'],r['spec'].replace('|','/'),r['package'],'1',price(r['budget_unit']),price(r['public_unit']),r['budget_status'],r['public_status'],r['code'] or '待选',source])+' |')
lines += ['', '## 换料与省成本关注点', '',
          '- ML307与ESP32的用户目标合计22元，已保存公开阶梯价合计37.01元，相差15.01元/台；应优先取得相同规格的供应商批量报价。',
          '- SIM卡座2.51元、功放公开参考4.52元、储能电容1.1262元、UPS电源切换芯片1.91元，是值得继续核查的项目。换料需核对电气参数及焊盘，不能直接按便宜价格替换。',
          '- 不同品牌、阻值、精度、封装及电容介质不能只凭同类名称合并。表内候选报价仅支持成本分析，未改变已验证固件。',
          '- 当前计划预算已高于50元/台，尚未计损耗、测试及运费。公开参考列大量项目仍缺价，不能据此宣布“全嘉立创采购”已经达到目标。',
          '', '## 未计入装配价格的位号', '', '| 位号 | 型号/用途 | 原因 |','|---|---|---|']
for r in data['excluded_refs']:
    lines.append(f'| {r["ref"]} | {r["model"]} | {r["reason"]} |')
lines += ['', '上述未装件、裸测试焊盘及安装孔不计购料费；外接模块也不计入本次主板价格。当前成本表不代表完成电气仿真、2A资格验证或工程签核。']
(HERE/'整板逐项价格表.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
with (OUT/'语音对讲主板逐项价格.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f)
    writer.writerow(['位号','用途','原规格','封装','数量','预算单价/元','公开参考单价/元','预算依据','公开价格依据','候选料号','来源','备注'])
    for r in rows:
        writer.writerow([r['ref'],r['role'],r['spec'],r['package'],1,r['budget_unit'],r['public_unit'],r['budget_status'],r['public_status'],r['code'],r['source'],r['note']])
print(json.dumps(summary,ensure_ascii=False,indent=2))
