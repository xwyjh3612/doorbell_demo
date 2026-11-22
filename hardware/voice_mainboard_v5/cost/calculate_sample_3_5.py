"""Separate public manufacturing fees from unquoted sample material budgets."""
from pathlib import Path
from decimal import Decimal as D
import json, shutil, collections
ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[2]
RAW=WORKSPACE/'build/v5-sample-cost-20261123'
OUT=ROOT/'sample-3-5';OUT.mkdir(exist_ok=True)
bom=json.loads((ROOT/'bom-budget.json').read_text(encoding='utf8'))
groups=collections.defaultdict(list)
for q in bom['parts']:
    if not q['populated'] or q.get('kind')=='reserved_interface':continue
    fp=q['footprint'];ref=q['ref']
    if ref.startswith('R'):label=q['value'].split()[0]+' '+fp+(' 0.1%' if '0.1%' in q['value'] else ' 1%')
    elif ref.startswith('C'):
        val=q['value'].split()[0]
        if ref in ['C19','C29']:val='10n'
        if ref in ['C20','C28']:val='100n'
        if ref=='C8':val=q['value']
        label=val+' '+fp
    elif ref.startswith('SW'):label='TACT TL3342-compatible'
    elif ref.startswith('J') and 'PinHeader' in fp:label=fp
    else:label=q['value'].split()[0]+' '+fp
    groups[label].append(ref)
tht={'J1','J14','J15','J16','J17','J18'}
assert len(groups)==37
assert sum(not tht.intersection(refs) for refs in groups.values())==33
material=D(str(bom['known_board_plus_UPS_allowance_material_cny']))+D('9')
rows=[]
for qty in [3,5]:
    raw=json.loads((RAW/f'jlc-smt-{qty}.json').read_text(encoding='utf-8-sig'))
    shutil.copy2(RAW/f'jlc-smt-{qty}.json',OUT/f'jlc-smt-{qty}.json')
    assert raw['response']['success']
    assert raw['parameters']['patchQuantity']==qty
    assert raw['parameters']['patchComponentType']==33
    prices={}
    for mode in ['economicTypeVO','standardTypeVO']:
        fees=raw['response']['data'][mode]
        ordinary=D(str(fees['totalMoney']))-D(str(fees['plateChangeMaterialCountMoney']))+D(str(fees['changeMaterielMoney']))
        prices[mode]={'returned_fees':fees,'ordinary_change_fee_reconstructed_cny':float(ordinary)}
    process=D(str(prices['standardTypeVO']['ordinary_change_fee_reconstructed_cny']))
    total=process+D('51.13')+material*qty
    rows.append({'assembled_quantity':qty,'PCB_order_quantity':5,'PCB_previous_public_quote_cny':51.13,
        'material_budget_per_board_cny':float(material),'material_budget_batch_cny':float(material*qty),
        'processing':prices,'conditional_total_cny':float(total)})
report={'date':'2026-11-23','PCB_sha256':bom['PCB_sha256'],'full_JLC_BOM_quote_obtained':False,
    'manufacturing_ready':False,'UPS_internal_circuit_complete':False,'placed_order':False,
    'SMT_components':80,'SMT_pads':373,'SMT_types':33,'THT_components':6,'THT_pads':20,'THT_types':4,
    'common_part_merge_exact_MPNs_qualified':False,'type_groups':dict(groups),
    'UPS_internal_unknown_parts_excluded_from_processing':True,
    'material_basis':'ML307C-DL19 from user1+ price; ESP12/UPS5 and other parts remain previous budgets; not full JLC purchasing prices.',
    'PCB_quote_date':'2026-11-22','PCB_quote_source':'https://www.jlc.com/newOrder/#/pcb/pcbPlaceOrder',
    'PCB_quote_record':'build/pcb-quote-2layer-5pcs-drill0.3.txt',
    'ordinary_fee_basis':'Replace whole-reel change fee included in returned totalMoney with returned ordinary changeMaterielMoney. Not an accepted order quote.',
    'three_assembled_boards_order_acceptance_confirmed':False,
    'excluded':['freight','minimum package and loss/replenishment not quoted','battery/NTC','adapter','speaker','microphone module','radar','housing','antenna/cables','programming and whole-unit tests'],
    'rows':rows}
(OUT/'estimate.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps([{'qty':r['assembled_quantity'],'process':r['processing']['standardTypeVO']['ordinary_change_fee_reconstructed_cny'],
    'material':r['material_budget_batch_cny'],'PCB':51.13,'conditional_total':r['conditional_total_cny']} for r in rows],indent=2))
