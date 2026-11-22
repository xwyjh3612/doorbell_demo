"""Summarize priced replacement candidates without changing the active PCB BOM.

Input is filtered public supplier data downloaded to build/. Use the price tier
for the actual number of each part, not the cheapest tier displayed. No candidate
is marked as production-qualified by this script.
"""
from pathlib import Path
import json,hashlib,urllib.parse
ROOT=Path(__file__).resolve().parent
research=Path('build/v4-low-cost-candidates')
def read(name):return json.loads((research/(name+'.json')).read_text(encoding='utf8'))
def choose(name,model=None,brand=None):
    return next(q for q in read(name)if (model is None or q['model']==model)and(brand is None or q['brand']==brand))
def price(q,quantity):
    pairs=sorted((int(n),float(v))for row in q['prices']for n,v in row.items())
    eligible=[pair for pair in pairs if pair[0]<=quantity]
    assert eligible
    return eligible[-1]
data=[]
selections=[
 ('sim_socket',choose('search0','NANO SIM 7P-Ow H1.45'),1,2.51,'SIM',
  'nano SIM candidate; supplier approval specification retrieved, exact pad drawing and card-detect mapping still missing; requires PCB footprint change'),
 ('sim_esd_array',choose('SRV05-4','SRV05-4','MSKSEMI'),1,3.41,'SRV05-4',
  'four I/O channels plus rail, SOT23-6; 5V VRWM; I/O-GND max0.50pF. Requires new layout, rail injection/power-off review, and ESD/read-card qualification'),
 ('esp_buck',choose('more7','SY8089A1AAC'),1,.8,'SY8089',
  '2.5-5.5V input/2A/0.6V feedback; EN1,GND2,LX3,IN4,FB5 matches current SOT23-5 pin assignment. Archived advanced specification; supplier current revision, loop/thermal/transient qualification pending'),
 ('modem_buck_conditional',choose('TPS563201','TPS563201DDCR','TI'),1,2.65,'TPS563201',
  '4.5-17V/3A, 0.768V FB, no PG pin. Not a direct replacement: external4.5V boundary fails guaranteed input after protection drops; revise UPS PG logic, divider, inductor/caps and PCB'),
 ('amplifier_not_preferred',choose('more0','NS4168'),1,3,'NS4168',
  'I2S ESOP8, 3.0-5.5V, headline2.5W at5V/4ohm versus MAX98357A~3.2W; current stock992<1000; channel, timing, gain and acoustic verification pending. Not preferred for this volume-sensitive project'),
]
for role,q,count,old,query,note in selections:
    quantity=1000*count;tier,unit=price(q,quantity)
    pdf={'sim_socket':'NANO-SIM-SHOUHAN','sim_esd_array':'SRV05-4-MSKSEMI','esp_buck':'SY8089A1AAC','modem_buck_conditional':'TPS563201-TI','amplifier_not_preferred':'NS4168'}[role]
    raw=(research/(pdf+'.pdf')).read_bytes()
    entry={'role':role,'model':q['model'],'brand':q['brand'],'package':q['spec'],
       'quantity_per_board':count,'purchase_quantity_for_1000_boards':quantity,
       'selected_public_tier_quantity':tier,'public_unit_cny':unit,'public_candidate_per_board_cny':unit*count,
       'current_budget_per_board_cny':old,'conditional_difference_per_board_cny':round(old-unit*count,5),
       'observed_stock':q['stock'],'stock_enough_for_1000':q['stock']>=quantity,
       'supplier':q.get('supplier','Shenzhen Huaqiu Electronics; public supplier listing'),
       'source':'https://www.taoic.com/item?w='+urllib.parse.quote(query),
       'supplier_datasheet_url':q['manual'],'datasheet_sha256':hashlib.sha256(raw).hexdigest(),
       'qualification':note,'production_qualified':False,'active_BOM_changed':False}
    data.append(entry)
baseline=json.loads((ROOT/'bom-budget.json').read_text(encoding='utf8'))
base=baseline['board_material_per_board_cny']
first=sum(q['conditional_difference_per_board_cny']for q in data if q['role']in ['sim_socket','sim_esd_array','esp_buck'])
second=first+next(q['conditional_difference_per_board_cny']for q in data if q['role']=='modem_buck_conditional')
report={'date':'2026-11-22','scope':'Other cost candidates only; wait for user UPS board before UPS selection',
 'currency':'CNY','baseline_PCB_sha256':baseline['PCB_sha256'],'baseline_material_per_board_cny':base,
 'supplier_final_quote_obtained':False,'active_BOM_changed':False,'candidates':data,
 'conditional_scenarios':[
   {'scope':'SIM socket + SIM ESD array + ESP buck only','saving_per_board_cny':round(first,5),'material_per_board_cny':round(base-first,5)},
   {'scope':'Also modem buck if protected 4.5V boundary and UPS controls redesigned/qualified','saving_per_board_cny':round(second,5),'material_per_board_cny':round(base-second,5)}],
 'scenario_exclusions':['PCB and assembly','tax/shipping/payment verification','minimum packs and scrap','new passive/layout adjustments','new UPS architecture'],
 'not_selected':[{'model':'ESD5V0D3B TECH PUBLIC','reason':'35pF junction capacitance in retrieved datasheet; not chosen as the low-capacitance SIM protection candidate'},
                 {'model':'PESD5V0S1UL,315','reason':'observed stock89, not adequate for4000pcs; not chosen solely from low headline price'}]}
(ROOT/'低价替代料核查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Conditional material:',report['conditional_scenarios'])
