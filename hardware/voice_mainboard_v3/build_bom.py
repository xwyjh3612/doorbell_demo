"""Saved PCB -> actual population/process counts and a source-priced BOM.

Machine assembly data is emitted from native CAD. Public unit references and
unquoted allowances stay separate; no fabricated volume discounts.
"""
from pathlib import Path
import json,re,collections,hashlib,csv,datetime
from urllib.parse import quote
import pcbnew as p
root=Path(__file__).resolve().parent;out=root/'cost';out.mkdir(exist_ok=True)
d=json.loads((root/'design.json').read_text(encoding='utf8'))
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
metadata={}
def walk(value,url=None):
    if isinstance(value,list):
        for x in value:walk(x,url)
    elif isinstance(value,dict):
        if value.get('id') and (value.get('offers')or value.get('data')):url='https://item.szlcsc.com/'+str(value['id'])+'.html'
        if isinstance(value.get('url'),str) and value['url'].startswith('https://item.szlcsc.com/'):url=value['url']
        if str(value.get('sku','')).startswith('C')and isinstance(value.get('offers'),dict):
            sku=value['sku'];metadata[sku]={'sku':sku,'name':value.get('name'),
              'url':url,'offers':value['offers'],'datasheet':value.get('datasheet')or value.get('subjectOf')}
        for x in value.values():
            if isinstance(x,(dict,list)):walk(x,url)
if (out/'public-sources.json').exists():walk(json.loads((out/'public-sources.json').read_text(encoding='utf8')))
for path in sorted(Path('build').glob('*.json*')):
    if not any(word in path.name for word in ['cost-','v3-','part-price']):continue
    try:
        text=path.read_text(encoding='utf8');walk(json.loads(text))
    except (json.JSONDecodeError,UnicodeError):
        try:
            for line in text.splitlines():
                if line.strip():walk(json.loads(line))
        except (ValueError,UnboundLocalError):pass
if (out/'extra-public-parts.json').exists():walk(json.loads((out/'extra-public-parts.json').read_text(encoding='utf8')))
by_mpn={v['name'].split(')')[-1].strip():v for v in metadata.values()if v.get('name')}
fps={f.GetReference():f for f in b.GetFootprints()};groups={};pending=[]
for x in d['parts']:
    ref=x['ref'];fp=fps[ref]
    if x['kind']=='mechanical' or ref.startswith('TP'):continue
    process='THT'if any(pd.GetAttribute()==p.PAD_ATTRIB_PTH for pd in fp.Pads())else 'SMT'
    expected_attribute=p.FP_THROUGH_HOLE if process=='THT'else p.FP_SMD
    assert fp.GetAttributes()&expected_attribute,'Native assembly technology flag mismatch: '+ref
    fid=fp.GetFPID()
    assert fid.GetLibItemName()==x['footprint'].split(':')[-1], 'BOM/PCB footprint mismatch: '+ref
    footprint=x['footprint']
    mpn=x.get('mpn') or x['value'].split(' C')[0]
    sku=x.get('lcsc')
    if not sku:
        match=re.search(r'\bC\d+\b',x['value']);sku=match[0]if match else None
    data=metadata.get(sku)if sku else by_mpn.get(mpn)
    if data is None and sku:
        # Preserve real observations already written during this design turn.
        # They are identified separately and have not been re-priced by quantity.
        observed=re.search(r'(?:Public|public)(\d+(?:\.\d+)?)CNY',x.get('note',''))
        stock=re.search(r'stock\s*(\d+)',x.get('note',''))
        if observed:
            data={'sku':sku,'name':mpn,'url':'https://so.szlcsc.com/global.html?k='+quote(mpn),
              'offers':{'price':float(observed[1]),'inventoryLevel':{'value':int(stock[1])if stock else None}},
              'observation_basis':'2026-11-22 public observation preserved in design.json '+ref+' note; not refreshed quantity quotation',
              'datasheet':{'url':x.get('source')}}
            metadata[sku]=data
    if data and not sku:sku=data['sku']
    key=(mpn,footprint,bool(x['dnp']),process)
    g=groups.setdefault(key,{'mpn':mpn,'lcsc':sku,'footprint':footprint,
        'dnp':bool(x['dnp']),'process':process,'refs':[],'quantity_per_board':0,'unique_electrical_pads_per_board':0,
        'sides':[],'unit_public_reference_cny':None,'unit_allowance_cny':None,'source':None,'stock':None,
        'procurement_status':x.get('procurement_status','land_and_stock_review_pending')})
    g['refs'].append(ref);g['quantity_per_board']+=1
    g['unique_electrical_pads_per_board']+=(len([pd for pd in fp.Pads()if pd.GetNumber()])if process=='THT'else len({pd.GetNumber()for pd in fp.Pads()if pd.GetNumber()}))
    side='B'if fp.IsFlipped()else'F'
    if side not in g['sides']:g['sides'].append(side)
    if data:
        g.update(unit_public_reference_cny=float(data['offers']['price']),source=data['url'],
          stock=data['offers'].get('inventoryLevel',{}).get('value'),
          price_basis=data.get('observation_basis','public_unit_reference_not_quantity_tier'))
        if sku=='C48982537':
            g['price_basis']='1000+ tier baseline; batch unit prices from user supplied ml307-user-price-tiers-20261122.json applied by build_cost.py'
    elif not g['dnp']:
        # Explicit estimation inputs, never supplier prices or final order totals.
        if ref.startswith('R'):allowance=.06 if '0.1%'in x['value']else .025
        elif ref.startswith('C'):allowance=.05
        elif ref.startswith('SW'):allowance=.2
        elif ref=='Q3':allowance=.335
        elif ref.startswith(('J','JP')):allowance=.15
        else:allowance=None
        g['unit_allowance_cny']=allowance;g['price_basis']='unquoted_allowance'
        pending.append(ref)
    x.update(mpn=mpn,lcsc=sku)
rows=sorted(groups.values(),key=lambda g:(g['dnp'],g['process'],g['mpn']))
active=[g for g in rows if not g['dnp']]
counts={process:{'types':len([g for g in active if g['process']==process]),
    'components':sum(g['quantity_per_board']for g in active if g['process']==process),
    'pads':sum(g['unique_electrical_pads_per_board']for g in active if g['process']==process)}for process in ['SMT','THT']}
priced=sum(g['quantity_per_board']*g['unit_public_reference_cny']for g in active if g['unit_public_reference_cny']is not None)
allowance=sum(g['quantity_per_board']*g['unit_allowance_cny']for g in active if g['unit_allowance_cny']is not None)
missing=[g['refs']for g in active if g['unit_public_reference_cny']is None and g['unit_allowance_cny']is None]
report={'revision':d['revision'],'source_pcb_sha256':hashlib.sha256((root/'voice_mainboard_v3.kicad_pcb').read_bytes()).hexdigest(),
 'date':'2026-11-22','currency':'CNY','counts':counts,'smt_sides':2,
 'physical_paste_apertures_not_double_counted_as_duplicate_EP_pins':True,
 'tht_switch_four_physical_leads_counted':True,
 'groups':rows,'public_reference_material_per_board_cny':round(priced,4),
 'unquoted_allowance_material_per_board_cny':round(allowance,4),
 'estimated_material_per_board_cny':round(priced+allowance,4)if not missing else None,
 'missing_without_allowance':missing,'unquoted_refs':pending,
 'final_supplier_quote':False,'extra_external_modules_included':False,
 'material_reference_basis':'ML307R-DL uses its 1000+ tier as BOM baseline only; build_cost.py adjusts each batch using user supplied tiers. Other parts remain public references or unquoted allowances.',
 'note':'Carrier PCBA only. ESP32-S3/INMP441/MAX98357 complete modules and power shunts/harnesses are separate mainboard-assembly lines. No battery/speaker/radar/enclosure/charger included.'}
(out/'bom-and-process.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(out/'public-sources.json').write_text(json.dumps([metadata[g['lcsc']]for g in active if g['lcsc']in metadata],ensure_ascii=False,indent=2)+'\n',encoding='utf8')
with (out/'assembly-bom.csv').open('w',encoding='utf-8-sig',newline='')as f:
    w=csv.writer(f);w.writerow(['Designator','Quantity','MPN','LCSC Part #','Footprint','Process','Side','DNP'])
    for g in rows:w.writerow([','.join(g['refs']),g['quantity_per_board'],g['mpn'],g['lcsc']or'',g['footprint'],g['process'],','.join(g['sides']),'YES'if g['dnp']else'NO'])
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in report.items()if k not in['groups','unquoted_refs']},ensure_ascii=True))
