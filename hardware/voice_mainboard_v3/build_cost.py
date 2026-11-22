"""Cost the saved V3 BOM and actual JLC double-side process configuration.

Cash quotation is not available. This publishes a traceable budget and keeps
module/assembly allowances, loss and unquoted engineering reserve explicit.
"""
from pathlib import Path
import json,hashlib,re
root=Path(__file__).resolve().parent;out=root/'cost'
bom=json.loads((out/'bom-and-process.json').read_text(encoding='utf8'))
assert not bom['missing_without_allowance']
assert bom['source_pcb_sha256']==hashlib.sha256((root/'voice_mainboard_v3.kicad_pcb').read_bytes()).hexdigest()
process=bom['counts'];smt_pads=process['SMT']['pads'];smt_types=process['SMT']['types']
tht_pads=process['THT']['pads'];tht_types=process['THT']['types']
pcb={}
for q in [5,100,1000]:
    record=out/(f'pcb-public-{q}.json'if q==1000 else f'pcb-public-{q}.txt')
    raw=record.read_text(encoding='utf8')
    if q==1000:
        public=json.loads(raw)
        assert public['quantity']==q and public['layers']==4 and public['drill']=='0.2'
        assert [x['value']for x in public['inputs']]==['10','7.5','1000']
        raw=public['pricing']
    match=re.search(r'预估支付总价\(不含运费\):\s*¥([\d.]+)',raw)
    assert match,'Public PCB total missing: '+str(record)
    pcb[q]=float(match[1])
modules=[{'item':'ESP32-S3完整开发板','unit_cny':20,'basis':'未询价预算，沿用开发板架构'},
 {'item':'INMP441完整麦克风模块','unit_cny':3.5,'basis':'未询价预算'},
 {'item':'MAX98357完整功放模块','unit_cny':3.5,'basis':'未询价预算'},
 {'item':'跳帽、线束','unit_cny':2,'basis':'未询价预算，电源跳帽料号和接触电阻待确认'},
 {'item':'模块插接、烧录与功能验收','unit_cny':5,'basis':'未询价人工预算，不含试验台和仪器购置'}]
module_unit=sum(x['unit_cny']for x in modules)
loss=.03;reserve=200;material=bom['estimated_material_per_board_cny'];rows=[]
tiers_record=json.loads((out/'ml307-user-price-tiers-20261122.json').read_text(encoding='utf8'))
ml307_tiers=next(x['tiers'] for x in tiers_record['models'] if x['lcsc']=='C48982537')
ml307_group=next(g for g in bom['groups'] if 'U1' in g['refs'])
assert ml307_group['lcsc']=='C48982537' and ml307_group['quantity_per_board']==1
ml307_base=ml307_group['unit_public_reference_cny']
def ml307_unit_for_quantity(quantity):
    return max((t for t in ml307_tiers if t['minimum_quantity']<=quantity),key=lambda t:t['minimum_quantity'])['unit_cny']
for q in [5,100,1000]:
    src=out/f'jlc-smt-{q}.json'
    raw=Path(f'build/smt-double-api-{q}-{smt_pads}-{smt_types}-{tht_pads}-{tht_types}.json')
    if raw.exists():
        v=json.loads(raw.read_text(encoding='utf8'));params=json.loads(v['request']);fees=v['data']['data']['standardTypeVO']
        assert params['patchLocation']=='TB' and params['patchQuantity']==q
        assert params['patchComponentQuantity']==smt_pads and params['patchComponentType']==smt_types
        assert params['plugInQuantity']==tht_pads and params['plugInType']==tht_types
        assert v['data']['data']['economicTypeVO']is None,'Double-side economic availability changed; review pricing'
        fields=['projectMoney','padMoney','manualPadMoney','manualWeldProjectMoney','changeMaterielMoney',
          'plateChangeMaterialCountMoney','steelMoney','packageMoney','singlePieceProcessingDifferenceFee','totalMoney']
        saved={'source':'https://www.jlc-smt.com/calc-online','date':'2026-11-22','parameters':params,
          'fees':{k:fees.get(k,0)for k in fields},'economic_double_side_available':False,
          'note':'Display total applies full-reel change-material discount. Budget uses undiscounted change fee.'}
        src.write_text(json.dumps(saved,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    saved=json.loads(src.read_text(encoding='utf8'));fees=saved['fees']
    params=saved['parameters']
    assert params['patchComponentQuantity']==smt_pads and params['patchComponentType']==smt_types
    assert params['plugInQuantity']==tht_pads and params['plugInType']==tht_types
    processing=fees['totalMoney']+fees['changeMaterielMoney']-fees['plateChangeMaterialCountMoney']
    ml307_unit=ml307_unit_for_quantity(q)
    quantity_material=material+(ml307_unit-ml307_base)
    carrier=pcb[q]+quantity_material*q+processing
    assembly=carrier+module_unit*q
    budget=assembly+quantity_material*q*loss+reserve
    rows.append({'quantity':q,'ml307_unit_cny':ml307_unit,'material_per_board_cny':round(quantity_material,4),
      'pcb_cny':pcb[q],'material_cny':round(quantity_material*q,4),
      'smt_and_tht_cny':round(processing,4),'carrier_subtotal_cny':round(carrier,4),
      'carrier_per_board_cny':round(carrier/q,4),'external_modules_assembly_cny':module_unit*q,
      'mainboard_assembly_subtotal_cny':round(assembly,4),'mainboard_assembly_per_board_cny':round(assembly/q,4),
      'loss_budget_cny':round(quantity_material*q*loss,4),'engineering_reserve_cny':reserve,
      'mainboard_budget_cny':round(budget,4),'budget_per_board_cny':round(budget/q,4)})
conditional=rows[-1]['mainboard_budget_cny']-(rows[-1]['ml307_unit_cny']-5)*1000*(1+loss)
data={'revision':bom['revision'],'date':'2026-11-22','currency':'CNY','source_pcb_sha256':bom['source_pcb_sha256'],
 'supplier_quote_obtained':False,'manufacturing_ready':False,'bom':bom,'module_allowances':modules,
 'module_allowance_per_board_cny':module_unit,'material_loss_budget_rate':loss,
 'engineering_reserve_per_batch_cny':reserve,'rows':rows,
 'ml307_condition':{'quantity':1000,'current_public_reference_cny':16.5,'unconfirmed_target_cny':5,
   'budget_if_target_obtained_cny':round(conditional,4),'budget_if_target_obtained_per_board_cny':round(conditional/1000,4),
   'verified_purchase_price':False},
 'pcb_source':'https://www.jlc.com/newOrder/#/pcb/pcbPlaceOrder',
 'pcb_public_records':['pcb-public-5.txt','pcb-public-100.txt','pcb-public-1000.json'],
 'pcb_parameters':{'size_mm':[100,75],'layers':4,'thickness_mm':1.6,'outer_oz':1,'inner_oz':.5,
   'min_drill_mm':.2,'actual_min_via_diameter_mm':.45,'finish':'HASL lead-free','color':'green',
   'auto_selected':'TG155 and four-wire low-resistance test','controlled_impedance_and_exact_stackup_quote_obtained':False},
 'excluded':['外壳','外置电池包及NTC','扬声器','外置雷达模块','5V适配器','运费'],
 'reserve_purpose':'指定叠层/阻抗、器件起订损耗、ML307装配工艺等未取得正式报价的预算预留；200元为假设，正式金额待DFM/BOM订单确认。',
 'volume_price_basis':'ML307R-DL按用户提供页面阶梯价：5只26.94、100只18.11、1000只16.50元；其余物料沿用公开参考和明确预算，尚未取得完整阶梯价。加工费按已有数量费率调整估算，尚无当前数量整单报价。',
 'ml307_tiers_source':'ml307-user-price-tiers-20261122.json',
 'production_target_80_cny_achieved':False}
(out/'estimate.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
lines=['# V3主板费用：按保存的PCB与BOM计算','',
 '2026-11-22修正：用户提供完整阶梯价后确认，原ML307R-DL的16.50元是1000只档位。5只应按26.94元/只、100只按18.11元/只，本表已重新计算。其余物料的页面参考价仍不代表完整采购阶梯价。本表总预算不等于厂家实际采购报价。','',
 f'2026-11-22。100×75mm四层、1.6mm，最小钻孔0.2mm，双面SMT。{smt_types}种SMT物料、{smt_pads}个贴片焊点；{tht_types}种插件、{tht_pads}个插件焊点。',
 '', '这是当前载板设计的预算，尚未取得整单报价或生产放行。板上集成ML307和UPS；ESP32-S3、麦克风、功放沿用完整模块并单独计入主板总成。',
 '', '| 项目 | 5片 | 100片 | 1000片 |','|---|---:|---:|---:|']
for label,key in [('ML307R-DL单价','ml307_unit_cny'),('PCB板费','pcb_cny'),('板载物料','material_cny'),('标准型双面SMT及插件','smt_and_tht_cny'),
 ('载板小计','carrier_subtotal_cny'),('每片载板','carrier_per_board_cny'),('外挂模块、线束、插接烧录验收','external_modules_assembly_cny'),
 ('主板总成小计','mainboard_assembly_subtotal_cny'),('每片主板总成','mainboard_assembly_per_board_cny'),
 ('3%物料损耗预算','loss_budget_cny'),('每批工程预留','engineering_reserve_cny'),('主板总成预算','mainboard_budget_cny'),('每片预算','budget_per_board_cny')]:
    lines.append('| '+label+' | '+' | '.join(f'{r[key]:,.2f}'for r in rows)+' |')
lines+=['', '币种人民币。含板上UPS控制器、连接器和按钮；不含外壳、电池包/NTC、喇叭、雷达、适配器及运费。',
 '', f'BOM基准材料金额{material:.4f}元/板含ML307R-DL的1000只档位16.50元；各批次按对应模组阶梯价调整。未询价电阻预算{bom["unquoted_allowance_material_per_board_cny"]:.4f}元/板。外挂模块/线束/插接烧录预算{module_unit:.2f}元/板，逐项在Excel中可改。',
 '', '公开PCB价格包含0.2mm孔工艺自动要求的TG155和四线低阻全测；指定叠层与±10%阻抗控制尚未获得正式报价。200元/批是工程与起订补差预算，不是嘉立创收费项目的确认金额。',
 '', '双面经济型在公开计算器返回不可用，采用标准型。旧公开响应的物料分类包含一次端子分类误差，原响应保留在processing-baseline文件；当前按实际128个SMT、23个插件及已有数量费率调整估算，49种SMT的换料费392元，整盘优惠245元，本预算恢复未享受优惠的147元差额。修正参数未取得新的公开计算器响应，手工工程/钢网/包装沿用观察值，正式金额待DFM配单。',
 '', 'ML307R-DL已按用户提供的商城阶梯价计算，来源保存在ml307-user-price-tiers-20261122.json；其余物料尚未取得完整阶梯价。C8/C9电容记录现货94只，L1现货21只、L2现货73只等不能直接支持大批量；厂商BOM配单、起订数量、供货周期和模块贴装工艺仍要复核。',
 '', f'1000片只有在ML307确实采购到5元/只时，按同一板子的条件预算为{conditional:,.2f}元，即{conditional/1000:.2f}元/片。5元是未确认目标，仍未达到整机80元目标。',
 '', '这版适合继续做工程复核和首板验证。当前载板与外挂模块架构按1000片复制也不会自动成为80元整机；量产版本需进一步集成ESP32/音频、减少测试排针与插件人工，并重新选定经验证的低成本电源物料后重新布板和核价。',
 '', '[查看BOM与工艺数据](bom-and-process.json) · [加工费5片](jlc-smt-5.json) · [加工费100片](jlc-smt-100.json) · [加工费1000片](jlc-smt-1000.json)',
 '', '[嘉立创PCB公开计算器](https://www.jlc.com/newOrder/#/pcb/pcbPlaceOrder) · [嘉立创SMT公开计算器](https://www.jlc-smt.com/calc-online)']
(out/'费用说明.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print(json.dumps({'rows':rows,'ml307_5_cny_conditional':data['ml307_condition']},ensure_ascii=True))
