"""Build a traceable candidate BOM/cost and review page from saved native CAD.

Unknown board/processing costs are left unset. No extrapolated JLC order quote.
"""
from pathlib import Path
import json,hashlib,collections,html,re
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v4.kicad_pcb'
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
prices=json.loads((ROOT/'cost/part-price-inputs.json').read_text(encoding='utf8'))
b=p.LoadBoard(str(file));fp={f.GetReference():f for f in b.GetFootprints()}
parts=[];groups=collections.defaultdict(float);counts={kind:{'components':0,'pads':0,'types':set()}for kind in ['SMT','THT']}
for q in d['parts']:
    if q['ref'].startswith(('TP','H')):continue
    entry=dict(q,**prices[q['ref']]);entry['populated']=not q['dnp'];parts.append(entry)
    if q['dnp']:continue
    groups[q['group']]+=entry['unit_cny']
    # ESP thermal drills do not convert an SMT RF module into a plug-in part.
    kind='SMT' if q['ref']=='U7' or fp[q['ref']].GetAttributes()&p.FP_SMD else 'THT'
    identity=q['mpn']
    if q['ref'].startswith(('R','C')) and not q.get('lcsc'):
        # Design comments such as "EN delay" are not separate purchased parts.
        nominal=q['value'].split()[0]
        tolerance='0.1%' if '0.1%' in q['value'] else '1%' if q['ref'].startswith('R') else 'unspecified'
        voltage=re.search(r'\b\d+V\b',q['value'])
        identity=(q['ref'][0],nominal,tolerance,voltage.group(0) if voltage else 'unspecified')
    c=counts[kind];c['components']+=1;c['types'].add((str(identity),q['footprint']))
    c['pads']+=sum(1 for pd in fp[q['ref']].Pads() if pd.IsOnLayer(p.F_Cu) and pd.GetAttribute()==(p.PAD_ATTRIB_SMD if kind=='SMT' else p.PAD_ATTRIB_PTH))
for c in counts.values():c['types']=len(c['types'])
material=sum(groups.values());mic=3.5
tiers={5:19,100:16.84,1000:16.45}
rows=[]
for quantity,modem_price in tiers.items():
    rows.append({'quantity':quantity,'user_procurement_target_material_per_board_cny':round(material,4),
                 'user_target_board_plus_microphone_material_cny':round(material+mic,4),
                 'C_DL_user_supplied_mall_tier_cny':modem_price,
                 'mall_modem_other_parts_unchanged_assumptions_material_cny':round(material-10+modem_price,4),
                 'bare_PCB_cny':None,'processing_cny':None,'final_supplier_quote_cny':None})
cost={'date':'2026-11-22','currency':'CNY','PCB_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
      'counts':counts,'groups_material_per_board_cny':dict(groups),'parts':parts,'rows':rows,
      'board_material_per_board_cny':round(material,4),'external_microphone_allowance_cny':mic,
      'target_50_achieved':False,'supplier_quote_obtained':False,
      'production_cost_constraint':d.get('production_cost_constraint'),
      'basis':'C-DL10/N8R8 12 user procurement targets; other parts historical page references or explicit unquoted allowances. No final cost quote.',
      'excluded_from_material':['bare PCB','SMT/THT','loss and minimum packs','programming/functional tests','protected battery/NTC','speaker','radar','adapter','housing','shipping']}
(ROOT/'cost/bom-budget.json').write_text(json.dumps(cost,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
md=['# V4主板预算与降本','',
    '本表对应当前保存的C-DL双层候选PCB。所有费用为人民币。ML307C-DL 10元和ESP32-S3-N8R8 12元是用户指定采购目标，其余混用历史参考与未询价预算；不是嘉立创整单报价。',
    '',f'板上默认物料合计 **{material:.2f}元/台**，未计PCB、SMT/插件、损耗和烧录验收。最新目标为1000台主板约50元，外设不计；INMP441外接模块预算 **{mic:.2f}元/台**单列，不占本次主板目标。当前不能宣称完整主板已压到50元。详见[量产1000台50元约束](量产1000台50元约束.md)。','',
    '| 模块 | 板上物料预算/台 |','|---|---:|']
md += [f'| {key} | {value:.2f} |' for key,value in groups.items()]
md += ['', '| 数量 | 10元C-DL目标下的板上物料/台 | 按商城C-DL档位、其余价格不变的条件物料/台 | PCB＋加工 |', '|---|---:|---:|---|']
md += [f"| {q['quantity']} | {material:.2f} | {q['mall_modem_other_parts_unchanged_assumptions_material_cny']:.2f} | 等最终布线/DFM后报价 |"for q in rows]
md += ['', '5片按商城模组19元、100片16.84元、1000片16.45元，均来自用户提供的C48972417页面文字；其它器件并未全部得到这些数量的档位。表格不得当作整单价格。',
       '',f"默认SMT {counts['SMT']['components']}个器件/{counts['SMT']['types']}类，SMT焊盘{counts['SMT']['pads']}个；插件{counts['THT']['components']}个/{counts['THT']['types']}类，插件焊盘{counts['THT']['pads']}个。ESP模组的散热过孔不是插件焊点。实际阶梯价、ML307装配工艺、整单服务和最小起订损耗以工厂BOM配单为准。",
       '', '## 降本顺序', '',
       '1. 保持双层、单面贴片和0.3mm常规孔径，减少开发板插接和线束；不能把V3四层报价当作这块双层板报价。',
       '2. 先核实模组与ESP采购版本及客供政策。10元C-DL/12元N8R8尚没有同条件供应商报价。',
       '3. 优先寻找兼容的低价SIM座和低电容SIM保护阵列。当前SIM座＋4个ESD预算5.92元，可作为重点候选；换料须核对封装、保护电压、电容和库存，未验证前不替换。',
       '4. 整体复核UPS和5V功放/雷达供电。目前采用具体器件的分支架构，功能及成本仍需优化；不能直接删去保护、低电关断或充电温度检测来凑50元。',
       '5. 若后续省电/供电简化需改变音频输出功率或备用时长，先量实际通话电流再调整；当前用户要求保持5V功放与2A输入。',
       '', '目标差额应以实际整板报价为准。单是当前板上物料已经超过50元，继续沿用本版全套器件并不会靠放大数量自动达到目标。',
       '', '详细每个参考价格、出处、位号、DNP和原生PCB SHA256见`bom-budget.json`。']
(ROOT/'cost/预算与降本.md').write_text('\n'.join(md)+'\n',encoding='utf8')

erc=json.loads((ROOT/'exports/erc.json').read_text(encoding='utf8'))
drc=json.loads((ROOT/'exports/routed-drc.json' if (ROOT/'exports/routed-drc.json').exists() else ROOT/'exports/pre-route-drc.json').read_text(encoding='utf8'))
status={'PCB_sha256':cost['PCB_sha256'],'layers':b.GetCopperLayerCount(),'size_mm':d['dimensions_mm'],
        'ERC':sum(len(s.get('violations',[])) for s in erc['sheets']),
        'DRC':len(drc['violations']),'unconnected':len(drc['unconnected_items']),
        'tracks_and_vias':len(list(b.GetTracks())),'manufacturing_ready':False,
        'production_cost_constraint':d.get('production_cost_constraint'),
        'power_load_qualified':False,'RF_USB_qualified':False,
        'low_battery_2A_drop_budget_passed':False,
        'open_items':d['assembly_open_items']}
(ROOT/'exports/validation.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def esc(s):return html.escape(str(s))
price_rows=''.join(f'<tr><td>{esc(k)}</td><td>¥{v:.2f}</td></tr>'for k,v in groups.items())
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲V4主板</title><style>
body{margin:0;background:#edf2f5;color:#18323b;font:16px/1.7 "Microsoft YaHei",Arial}main{max-width:1260px;margin:0 auto;padding:28px}h1{font-size:32px;margin:0}h2{font-size:21px}.sub{color:#637882}.note{background:#fff1d7;padding:16px;border-radius:12px}.grid{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-top:20px}.card{background:white;border-radius:16px;padding:22px}.stats{display:flex;gap:16px;flex-wrap:wrap}.stats>div{background:white;border-radius:12px;padding:16px;flex:1;min-width:150px}.stats b{font-size:25px;display:block}img{width:100%;height:auto}table{width:100%;border-collapse:collapse;font-size:14px}td{padding:9px;border-bottom:1px solid #e3eaee}button,a{color:#09675e}button{padding:7px 12px;background:white;border:1px solid #cad8df;border-radius:7px;cursor:pointer}#board{overflow:auto;max-height:650px}#board img{min-width:650px}a{margin-right:15px}.ports{padding-left:18px}.ports li{margin-bottom:10px}@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:16px}}</style><main>
<div class="sub">VOICE INTERCOM · V4 ENGINEERING</div><h1>ESP32-S3＋ML307C-DL 主板</h1><p class="sub">双层主板 · 单面贴片 · 1000台主板含加工约50元目标 · 不含外设</p>
<p class="note">工程候选，尚未生产放行。下方来自当前保存的PCB，连接检查结果不代表完整电源、射频、USB及实机通话已经验收。</p>
<div class="stats"><div><b>100 × 75 mm</b>双层 / 单面SMT</div><div><b>5V / 2A</b>4.5～5.5V边界待验收</div><div><b>ERC __ERC__ / DRC __DRC__</b>未连接 __UNCONNECTED__</div><div><b>¥__MATERIAL__</b>板上条件物料预算 / 不含加工</div></div>
<div class="grid"><section class="card"><h2>实际PCB</h2><button onclick="view('front.svg')">正面</button> <button onclick="view('back.svg')">背面</button> <button onclick="zoom(1.25)">放大</button> <button onclick="zoom(.8)">缩小</button><div id="board"><img id="pcb" src="front.svg" alt="当前原生PCB正面"></div><p><a href="schematic.svg" target="_blank">完整原理图</a><a href="validation.json">检查记录</a><a href="bom.json">逐项BOM与预算</a></p></section>
<aside class="card"><h2>接口</h2><ul class="ports"><li>J1：中心正极5.5/2.5mm圆口</li><li>J2/J4：受保护1S电池＋10k NTC</li><li>J18：GND / TX43 / RX44 / 5V TTL</li><li>J16：可选雷达，5V/GND/RX6/TX8</li><li>J14：INMP441麦克风小模块</li><li>J15：功放BTL喇叭＋/−</li><li>BOOT呼叫键、复位键、外部按钮</li><li>USB维修与ESP Host互斥0Ω选装</li></ul><p class="sub">USB联网适配、新C-DL AT固件与长通话尚未实测。官方ESP通话协议和主动丢旧包代码未修改。</p></aside></div>
<div class="grid"><section class="card"><h2>供电</h2><p>低价圆口接5V/2A适配器，保留4.5～5.5V设计余量。外电 → 3.792V降压 → 双源切换；电池 → 欠压开关 → 双源切换。主总线分别供4G、ESP 3.3V降压、音频5V升压。</p><p>充电约100mA，ESP ADC粗估电量。欠压控制已运行ngspice行为模型与容差计算；真实稳压闭环、2A瞬态、低电切换和温升尚未验收。</p><p class="note">C-DL库引脚与焊盘已核对，厂家完整硬件手册、电平时序、钢网及实物仍需复核。</p></section><section class="card"><h2>物料预算</h2><table>__ROWS__</table><p>板上物料条件预算¥__MATERIAL__，还需PCB、贴装、损耗和功能测试。外接麦克风¥3.50单列，不计入本次50元主板目标。</p><p class="sub">C-DL ¥10 / ESP ¥12为用户采购目标。其余是历史参考或未询价预算，尚未达到50元完整主板目标。</p></section></div>
<p class="sub">C-DL符号/封装来源：嘉立创EDA/EasyEDA官方库。<a href="https://lceda.cn/">嘉立创EDA</a><a href="https://easyeda.com/">EasyEDA</a>来源记录随工程保存。</p></main><script>let factor=1;function view(s){document.getElementById('pcb').src=s}function zoom(z){factor=Math.min(4,Math.max(.75,factor*z));document.getElementById('pcb').style.width=(factor*100)+'%'}</script></html>'''
for key,value in {'__ERC__':status['ERC'],'__DRC__':status['DRC'],'__UNCONNECTED__':status['unconnected'],
                  '__MATERIAL__':f'{material:.2f}','__ALL__':f'{material+mic:.2f}','__ROWS__':price_rows}.items():page=page.replace(key,str(value))
(ROOT/'exports/review.html').write_text(page,encoding='utf8')
print(json.dumps({'checks':status,'counts':counts,'material_budget':material,'microphone_allowance':mic},ensure_ascii=False,indent=2))
