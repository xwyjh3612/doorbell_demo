"""Reconcile saved public references and quantify conditional cost options.

No catalogue substitutions are silently written into the PCB or schematic.
Avoid double-counting header price savings when the header is not populated.
"""
import copy,hashlib,json
from decimal import Decimal as D
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
OUT=ROOT/'cost'
old=json.loads((ROOT.parent/'voice_mainboard_v6/cost/整板逐项价格.json').read_text(encoding='utf-8'))
rows=copy.deepcopy(old['rows']);byref={r['ref']:r for r in rows}
for r in rows:
    r['revised_unit']=r['public_unit']if r['public_unit']is not None else r['budget_unit']
    r['revised_basis']='公开/历史候选参考，尚未完成器件资格核查'if r['public_unit']is not None else r['budget_status']
    r['procurement_qualified']=False
for ref in ['U1','U7']:
    byref[ref]['revised_unit']=byref[ref]['budget_unit']
    byref[ref]['revised_basis']='用户目标采购价，未取得批量报价；不是嘉立创价'

simdata=json.loads((REPO/'build/v6-price-recheck-20261124/SIM卡座.json').read_text(encoding='utf-8'))
sim=next(r for r in simdata['records']if r['code']=='C720512')
simtier=next(t for t in sim['tiers']if t['start']<=1000 and(t['end']<0 or 1000<=t['end']))
assert sim['model']=='SMN-305-ARP7' and sim['stock']>=1000
simrow=byref['J10']
simrow.update(revised_unit=simtier['cny'],revised_basis='国产翻盖Nano SIM候选；图纸/检测触点/封装仍待核，未换入PCB',candidate_model=sim['model'],code=sim['code'],source=sim['page'],evidence='build/v6-price-recheck-20261124/SIM卡座.json',candidate_stock=sim['stock'])

resdata=json.loads((REPO/'build/v6-price-recheck-20261124/0603WAF1003T5E.json').read_text(encoding='utf-8'))
res=next(r for r in resdata['records']if r['model']=='0603WAF1003T5E')
refs=['R32','R5','R6','R8','R15','R16','R18','R20','R59','R69']
quantity=1000*len(refs)
assert res['stock']>=quantity and res['encapsulation']=='0603'
tier=next(t for t in res['tiers']if t['start']<=quantity and(t['end']<0 or quantity<=t['end']))
for ref in refs:
    r=byref[ref]
    assert r['package']=='R_0603_1608Metric'and '0.1%'not in r['spec']
    r.update(revised_unit=tier['cny'],revised_basis='100k/1%/0603候选，合并采购10000颗；功率/温度系数/库别待核',code=res['code'],candidate_model=res['model'],source=res['page'],evidence='build/v6-price-recheck-20261124/0603WAF1003T5E.json',candidate_stock=res['stock'])

def total(items):return sum((D(str(r['revised_unit'])) for r in items),D('0'))
material=total(rows);pcb=D(str(old['summary']['pcb_unit']));assembly=D(str(old['summary']['assembly_unit']))
regular=material+pcb+assembly
lowrows=[r for r in rows if r['ref']not in ['J16','J18']]
lowmat=total(lowrows)
historical=json.loads((ROOT.parent/'voice_mainboard_v6/cost/jlc-smt-1000-v6.json').read_text(encoding='utf-8'))
fee=historical['response']['data']['standardTypeVO']
# Only the THT labor sensitivity is counted. No additional saving in setup,
# SMT types, basic-library discount or minimum processing is assumed.
pad_rate=D(str(fee['manualPadMoney']))/D('23000')
assert pad_rate==D('.09')
labor_saving=pad_rate*8
lowassembly=assembly-labor_saving
lowboard=lowmat+pcb+lowassembly

report={'date':'2026-11-24','quantity':1000,'product':'语音对讲主板V7','pcb_sha256':hashlib.sha256((ROOT/'voice_mainboard_v7.kicad_pcb').read_bytes()).hexdigest(),'final_supplier_quote':False,'substitutions_applied_to_CAD':False,'manufacturing_ready':False,'target_chip_prices':{'U1':10,'U7':12},'rows':rows,'summary':{'old_budget_board':old['summary']['budget_board'],'reference_material_with_target_chips_and_candidates':float(material),'pcb_historical_unit':float(pcb),'assembly_historical_unit':float(assembly),'full_headers_conditional_board':float(regular),'production_material_without_J16_J18':float(lowmat),'production_assembly_sensitivity_unit':float(lowassembly),'production_conditional_board':float(lowboard),'full_headers_batch':float(regular*1000),'production_batch':float(lowboard*1000),'header_material_saving':float(material-lowmat),'THT_labor_sensitivity_saving':float(labor_saving),'gain_vs_old_budget_production':float(D(str(old['summary']['budget_board']))-lowboard),'amp_price_used':byref['U14']['revised_unit'],'public_chip_price_premium':15.01,'full_headers_with_public_chip_prices':float(regular+D('15.01')),'production_with_public_chip_prices':float(lowboard+D('15.01'))},'unquoted_or_target_refs':[r['ref']for r in rows if r['public_unit']is None or r['ref']in ['U1','U7']],'unavailable_quote_attempt':'assembly-options-powershell.json: calculator returned a web security challenge, no fresh quote obtained; sensitivity uses saved 2026-11-24 fees only.','blocked_substitution':{'10k_candidate':'C25804','observed_stock':118,'required_quantity':10000,'action':'库存不足，未纳入新降本方案；10k普通电阻继续原预算'},'production_population_options':{'prototype':'保留现有全部116个元件及雷达、TTL排针','low_cost_optional':'114个元件；仅J16雷达排针与J18 TTL排针不装。焊孔/网络保留；TTL用测试夹具或按需要补焊，雷达款补装J16。需对应工装/选装物料。'},'scope':old['scope']}
(OUT/'量产降本核算.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

lines=['# 语音对讲主板：背面整理与量产降本核算','', '2026-11-24；1000块、100×75mm、两层、单面贴片。PCB走线已整理，以下采购替代尚未写入CAD。','',
       '**核算仍是有条件的规划值：4G按10元、ESP32-S3 N8R8按12元目标采购价；其他优先使用已保存的公开/历史参考，未核价项目保留原预算。没有取得嘉立创完整审单报价。**','',
       '| 配置 | 材料/元 | PCB/元 | 加工/元 | 每块合计/元 | 1000块/元 |','|---|---:|---:|---:|---:|---:|',
       f'| 原全接口规划预算 | 45.7157 | {pcb:.4f} | {assembly:.4f} | {old["summary"]["budget_board"]:.4f} | {old["summary"]["budget_board"]*1000:.2f} |',
       f'| 核查参考价及国产SIM候选，保留全部排针 | {material:.4f} | {pcb:.4f} | {assembly:.4f} | {regular:.4f} | {regular*1000:.2f} |',
       f'| 上述候选＋雷达/TTL仅预留焊孔的可选量产配置 | {lowmat:.4f} | {pcb:.4f} | {lowassembly:.4f} | {lowboard:.4f} | {lowboard*1000:.2f} |','',
       '加工基础来自此前公开计算器；去掉8个插件焊点，按历史0.09元/焊点估计节省0.72元/台。不额外假设换料补贴，也不把它称为本次新报价。此次API返回网站防护页面，未取得新计算结果。44类贴片仍为未完成料号合并的旧参数。','',
       '## 可核查的具体差额','', '| 项目 | 原预算/元 | 候选参考/元 | 差額/台 | 状态 |','|---|---:|---:|---:|---|']
groups=[('国产翻盖Nano SIM卡座',['J10']),('12颗100nF/0603',['C11','C13','C14','C15','C16','C17','C18','C20','C28','C58','C62','C26']),('2颗10µF/0805',['C10','C61']),('10颗100k/1%/0603',refs),('3颗电平转换',['U3','U4','U5']),('4颗2N7002K-7',['Q1','Q2','Q4','Q5']),('BSS84,215',['Q3']),('5个原有排针采购价',['J14','J15','J16','J17','J18']),('功放参考价纠正',['U14'])]
for label,rr in groups:
    before=sum(D(str(byref[r]['budget_unit']))for r in rr);after=sum(D(str(byref[r]['revised_unit']))for r in rr)
    status='图纸/封装/检测触点待核，未换入'if 'J10'in rr else '当前料号价格参考；仍需下单核价'if any(r.startswith('U')or r.startswith('Q')for r in rr)else '候选规格/库存/SMT库别待采购审核'
    if 'U14'in rr:status='由3元预算改用4.52元公开参考；此项增加1.52元，已计入总价'
    lines.append(f'| {label} | {before:.4f} | {after:.4f} | {before-after:+.4f} | {status} |')
lines+=['','表内项目是主要差额，并非只把降价项相加：完整总价逐行重算，包含Q6、J11等参考价增加项，避免低估。排针不装时按候选参考价扣除0.1514元，不能再次扣除原预算0.30元。','',
        '## 成本还差多少','',f'- 可选量产配置距50元目标约{lowboard-D("50"):.2f}元/块；这是尚未计运费、损耗、测试和夹具的有条件预算。',
        f'- 若4G和ESP均按已保存嘉立创公开参考价采购，需增加15.01元/块；可选量产配置约{lowboard+D("15.01"):.2f}元/块，且仍含未核价项目，不能称为全嘉立创完整报价。',
        '- 目前最大机会仍是取得同规格4G/ESP批量报价，以及剩余连接器的贴片/装配方案。继续缩小PCB要先重排主控、音频、USB分区并重新核机械尺寸，尚不计未报价的面积节省。',
        '- 去掉拐弯本身不减少贴装物料或板面积；本次清理不计PCB价格下降。保持两层、100×75mm与既有功能。',
        '- 10k候选C25804公开库存仅118颗，1000板约需10000颗，未采用该价格压低成本。',
        '- 不以删减电池保护、NTC、必要去耦、电源切换和独立3.8V/3.3V电源来凑50元。','',
        '## 逐项重算清单','', '| 位号 | 规格/原型号 | 本方案单价/元 | 候选料号 | 依据与未完成项 | 来源 |','|---|---|---:|---|---|---|']
for r in rows:
    link=f'[参考页面]({r["source"]})'if r['source']else'未取得报价'
    lines.append(f'| {r["ref"]} | {r["spec"].replace("|","/")} | {r["revised_unit"]:.5f} | {r["code"]or"待选"} | {r["revised_basis"]} | {link} |')
lines+=['',old['scope'],'', '[机器可读核算](量产降本核算.json) · [当前PCB](../voice_mainboard_v7.kicad_pcb) · [背面前后对比](../exports/review.html)']
(OUT/'量产降本核算.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(report['summary'],ensure_ascii=False,indent=2))
