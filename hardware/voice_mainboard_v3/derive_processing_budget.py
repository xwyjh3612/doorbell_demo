"""Adjust observed JLC fees to corrected physical assembly counts.

The corrected count is not a fresh supplier response. Keep the original API
observations and identify each unchanged/rate-derived assumption explicitly.
"""
from pathlib import Path
import json
root=Path(__file__).resolve().parent;out=root/'cost'
counts=json.loads((out/'bom-and-process.json').read_text(encoding='utf8'))['counts']
for q in [5,100,1000]:
    original_path=Path(f'build/smt-double-api-{q}-433-50-95-7.json')
    if not original_path.exists():original_path=out/f'processing-baseline-{q}.json'
    original=json.loads(original_path.read_text(encoding='utf8'))
    old=json.loads(original['request']);fees=original['data']['data']['standardTypeVO']
    baseline=out/f'processing-baseline-{q}.json'
    baseline.write_text(json.dumps(original,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    params=dict(old,patchComponentQuantity=counts['SMT']['pads'],patchComponentType=counts['SMT']['types'],
      plugInQuantity=counts['THT']['pads'],plugInType=counts['THT']['types'])
    rates={'smt_per_pad':fees['padMoney']/(q*old['patchComponentQuantity']),
      'tht_per_pad':fees['manualPadMoney']/(q*old['plugInQuantity']),
      'change_material_per_type':fees['changeMaterielMoney']/old['patchComponentType'],
      'discounted_change_per_type':fees['plateChangeMaterialCountMoney']/old['patchComponentType']}
    f=dict(fees)
    f.update(padMoney=round(q*params['patchComponentQuantity']*rates['smt_per_pad'],4),
      manualPadMoney=round(q*params['plugInQuantity']*rates['tht_per_pad'],4),
      changeMaterielMoney=round(params['patchComponentType']*rates['change_material_per_type'],4),
      plateChangeMaterialCountMoney=round(params['patchComponentType']*rates['discounted_change_per_type'],4))
    minimum=fees['singlePieceProcessingDiffFeeDetailVO']['minimumSinglePieceProcessingFee']
    old_diff=max(0,q*minimum-fees['projectMoney']-fees['changeMaterielMoney']-fees['padMoney'])
    assert abs(old_diff-fees['singlePieceProcessingDifferenceFee'])<.001
    f['singlePieceProcessingDifferenceFee']=round(max(0,q*minimum-f['projectMoney']-f['changeMaterielMoney']-f['padMoney']),4)
    selected=['projectMoney','padMoney','manualPadMoney','manualWeldProjectMoney','changeMaterielMoney',
      'plateChangeMaterialCountMoney','steelMoney','packageMoney','singlePieceProcessingDifferenceFee']
    f['totalMoney']=round(sum(f[k]for k in ['projectMoney','padMoney','manualPadMoney','manualWeldProjectMoney',
      'plateChangeMaterialCountMoney','steelMoney','packageMoney','singlePieceProcessingDifferenceFee']),4)
    selected.append('totalMoney')
    derived={'source':'https://www.jlc-smt.com/calc-online','date':'2026-11-22','parameters':params,
      'fees':{k:f[k]for k in selected},'economic_double_side_available':False,
      'fresh_calculator_response_for_these_parameters':False,'pricing_basis':'rate-adjusted_budget_from_observed_API_fees',
      'baseline_record':baseline.name,'observed_unit_rates':rates,
      'assumptions':['2 fewer SMT pads, one fewer SMT type; battery terminal adds 2 THT pads and one THT type.',
        'Use the same quantity-specific pad rates; manual engineering, PCB size, steel and package fees retained.',
        'Minimum per-board processing difference follows the formula that exactly reproduces each original response.',
        'Corrected public-calculator refresh unavailable (browser host unavailable; direct request returned web anti-automation page).',
        'This adjustment is an estimate; current parameters require a fresh final DFM/BOM/order quotation.'],
      'note':'Original response preserved separately. Display discount is restored to full change-material fee in the main budget.'}
    (out/f'jlc-smt-{q}.json').write_text(json.dumps(derived,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(q,'current-count processing estimate',round(f['totalMoney']+f['changeMaterielMoney']-f['plateChangeMaterialCountMoney'],4))
