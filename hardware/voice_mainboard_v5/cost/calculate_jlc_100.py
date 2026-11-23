"""Recalculate the 100-board budget without labelling unquoted items as JLC prices."""
from pathlib import Path
from decimal import Decimal as D
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'jlc-100'
bom = json.loads((ROOT / 'bom-budget.json').read_text(encoding='utf8'))
market = json.loads((OUT / 'public-part-prices.json').read_text(encoding='utf8'))
raw = json.loads((OUT / 'jlc-smt-100.json').read_text(encoding='utf-8-sig'))
assert raw['response']['success']
assert raw['parameters']['patchQuantity'] == 100
fees = raw['response']['data']['standardTypeVO']
processing = D(str(fees['totalMoney'])) - D(str(fees['plateChangeMaterialCountMoney'])) + D(str(fees['changeMaterielMoney']))
quoted_refs = set()
parts_total = D('0')
for row in market['rows']:
    qty = 100 * len(row['refs'])
    tier = next(t for t in row['tiers'] if t['start'] <= qty and (t['end'] < 0 or qty <= t['end']))
    row['purchase_quantity_before_loss'] = qty
    row['applicable_unit_cny'] = tier['unit_cny']
    row['batch_cny'] = float(D(str(tier['unit_cny'])) * qty)
    parts_total += D(str(row['batch_cny']))
    assert not quoted_refs.intersection(row['refs'])
    quoted_refs.update(row['refs'])
unknown = [p for p in bom['parts'] if p['populated'] and p.get('kind') != 'reserved_interface' and p['ref'] not in quoted_refs]
unknown_budget = sum((D(str(p['unit_cny'])) * 100 for p in unknown), D('0'))
pcb = D('561')
ups_budget = D('500')
known = parts_total + processing + pcb
report = {
    'date': '2026-11-23', 'quantity': 100, 'currency': 'CNY',
    'PCB_sha256': bom['PCB_sha256'],
    'full_JLC_BOM_quote_obtained': False, 'placed_order': False,
    'manufacturing_ready': False, 'UPS_internal_circuit_complete': False,
    'ordinary_processing_public_calculator_cny': float(processing),
    'PCB_previous_public_quote_cny': float(pcb),
    'PCB_quote_date': '2026-11-22',
    'PCB_quote_source': 'https://www.jlc.com/newOrder/#/pcb/pcbPlaceOrder',
    'PCB_quote_record': 'pcb-100-public-quote.txt',
    'public_priced_parts_batch_cny': float(parts_total),
    'public_priced_parts_ref_count': len(quoted_refs),
    'known_priced_subtotal_cny': float(known),
    'remaining_parts_historical_budget_batch_cny': float(unknown_budget),
    'remaining_parts_without_verified_JLC_price': [{'ref': p['ref'], 'value': p['value'], 'per_board_budget_cny': p['unit_cny']} for p in unknown],
    'UPS_user_material_allowance_batch_cny': float(ups_budget),
    'conditional_mainboard_budget_excluding_UPS_cny': float(known + unknown_budget),
    'conditional_mainboard_budget_with_UPS_allowance_cny': float(known + unknown_budget + ups_budget),
    'conditional_per_board_with_UPS_allowance_cny': float((known + unknown_budget + ups_budget) / 100),
    'ordinary_processing_basis': 'Returned totalMoney includes whole-reel change fee; replace it with ordinary changeMaterielMoney. Exact order/BOM/discount not accepted.',
    'UPS_unknown_internal_components_and_processing_excluded': True,
    'part_selection_and_footprint_qualification_complete': False,
    'exclusions': ['freight', 'minimum package purchase and assembly loss', 'UPS unknown internal processing', 'programming and whole-unit test', 'battery/NTC', 'adapter', 'speaker', 'microphone module', 'radar', 'housing', 'antenna/cables'],
    'rows': market['rows'],
}
(OUT / 'estimate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps({k: report[k] for k in ['public_priced_parts_batch_cny', 'ordinary_processing_public_calculator_cny', 'PCB_previous_public_quote_cny', 'known_priced_subtotal_cny', 'remaining_parts_historical_budget_batch_cny', 'conditional_mainboard_budget_with_UPS_allowance_cny']}, ensure_ascii=False, indent=2))
