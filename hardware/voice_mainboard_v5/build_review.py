"""Build review/cost artifacts from current saved native CAD and fresh checks."""
from pathlib import Path
from decimal import Decimal as D
import collections,hashlib,html,json,re,zipfile
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
data=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
prices=json.loads((ROOT/'cost/part-price-inputs.json').read_text(encoding='utf8'))
board=p.LoadBoard(str(file))
fps={f.GetReference():f for f in board.GetFootprints()}
parts=[];groups=collections.defaultdict(lambda:D(0))
counts={'SMT':{'components':0,'pads':0},'THT':{'components':0,'pads':0}}
for q in data['parts']:
    if q['ref'].startswith(('TP','H')):continue
    part=dict(q,**prices[q['ref']],populated=not q['dnp'])
    parts.append(part)
    if q['dnp']:continue
    groups[q['group']]+=D(str(part['unit_cny']))
    if q['kind']=='reserved_interface':continue
    kind='SMT' if fps[q['ref']].GetAttributes()&p.FP_SMD else 'THT'
    counts[kind]['components']+=1
    counts[kind]['pads']+=sum(1 for pad in fps[q['ref']].Pads() if pad.GetNumber() and pad.IsOnLayer(p.F_Cu) and pad.GetAttribute()==(p.PAD_ATTRIB_SMD if kind=='SMT' else p.PAD_ATTRIB_PTH))
material=sum(groups.values(),D(0))
fees={'PCB':D('2.50'),'SMT_THT':D('3.50'),'loss_programming_test':D('2.50')}
assembled=material+sum(fees.values(),D(0))
cheap_sim_difference=D('2.51')-D('0.60960')
assert material==D('44.09096'),material
sha=hashlib.sha256(file.read_bytes()).hexdigest()
cost={'date':'2026-11-22','quantity':1000,'currency':'CNY','PCB_sha256':sha,
    'physical_installed_counts_excluding_UPS_contract':counts,
    'groups_material_per_board_cny':{k:float(v) for k,v in groups.items()},'parts':parts,
    'known_board_plus_UPS_allowance_material_cny':float(material),
    'unknown_UPS_integrated_material_allowance_cny':5,'UPS_actual_parts_list_complete':False,
    'manufacturing_allowances_cny':{k:float(v) for k,v in fees.items()},
    'assembled_allowance_per_board_cny':float(assembled),'1000_boards_allowance_cny':float(assembled*1000),
    'if_cheap_SIM_qualified_assembled_per_board_cny':float(assembled-cheap_sim_difference),
    'supplier_final_quote_obtained':False,'manufacturing_ready':False,
    'basis':'ML30710/ESP12/UPS5 user allowances; researched3 cheap ICs; JAE socket2.51 retained; old passive budgets. PCB/assembly/test unquoted.',
    'excludes':['adapter','battery/NTC','housing','speaker','external microphone module','radar module','cables','tax/freight not established']}
(ROOT/'cost/bom-budget.json').write_text(json.dumps(cost,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
erc=json.loads((ROOT/'exports/erc.json').read_text(encoding='utf8'))
drc=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
audit=json.loads((ROOT/'exports/design-audit.json').read_text(encoding='utf8'))
assert audit['PCB_sha256']==sha
model=json.loads((ROOT/'exports/modem-buck-model/result.json').read_text(encoding='utf8'))
status={'PCB_sha256':sha,'layers':2,'size_mm':[100,75],
    'ERC':sum(len(s.get('violations',[])) for s in erc['sheets']),
    'DRC':len(drc['violations']),'unconnected':len(drc['unconnected_items']),
    'tracks_and_vias':len(board.GetTracks()),'native_pin_contract_passed':audit['native_pin_contract_passed'],
    'UPS_output_is_5V_user_assumption':True,'UPS_internal_circuit_complete':False,
    'cheap_SIM_socket_footprint_complete':False,'power_load_qualified':False,'RF_USB_qualified':False,
    'TI_PSpice_model_completed_in_ngspice':model['model_completed'],
    'full_motherboard_simulated':False,'manufacturing_ready':False,'firmware_changed':False,
    'assembled_allowance_cny':float(assembled),'open_items':data['assembly_open_items']}
(ROOT/'exports/validation.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
lines=['# V5主板量产预算','',
    f'当前后级主板已定材料＋UPS5元额度 **{material:.2f}元/台**，制造预算8.50元，主板合计 **{assembled:.2f}元/台**，1000台 **{assembled*1000:.2f}元**。UPS内部器件未定，5元不是一套已批准的详细BOM。',
    '', '| 部分 | 每台材料/元 |','|---|---:|']
lines += [f'| {k} | {v:.5f} |' for k,v in groups.items()]
lines += [f'| **材料合计** | **{material:.5f}** |','',
    '| 制造费用预算 | 每台/元 |','|---|---:|',
    '| 100×75mm双层PCB | 2.50 |','| SMT/插件 | 3.50 |','| 损耗、烧录、测试 | 2.50 |',
    f'| **完整主板预算** | **{assembled:.5f}** |','',
    f'与前一轮50.90246元方案相比：暂保留JAE卡座增加1.90040元；SY8089前馈电容增加0.05元；一颗额外22μF输入电容改默认不贴减少0.26190元，得到{assembled:.5f}元。SIM候选拿到焊盘图并通过验收后，条件主板预算 **{assembled-cheap_sim_difference:.5f}元/台**。',
    '', f"当前已定物理件：SMT {counts['SMT']['components']}颗/{counts['SMT']['pads']}前铜焊盘，插件{counts['THT']['components']}颗/{counts['THT']['pads']}焊盘；UPS接口六个焊线孔和未来未知IC另计，不能用当前焊点数报价完整集成UPS后的SMT。",
    '', '价格依据：ML30710元、ESP12元、UPS5元为用户目标；TPS563201/SY8089/SRV05-4采用保存的公开1000台适用档位，其余沿用历史预算。PCB和制造均为未询价额度，税运、客供、最小包装和一次性工程费未确认。',
    '', '不含外部适配器、电池/NTC、外壳、喇叭、麦克风模块、雷达及线束。未知UPS内部零件待识别后替换5元额度，不重复把被删除的旧UPS/音频升压加回。',
    '', '## 逐项材料','', '| 位号 | 型号/参数 | 默认贴装 | 每颗/预算组元 |','|---|---|---|---:|']
lines += [f"| {q['ref']} | {q['value']} | {'是' if q['populated'] else 'DNP'} | {q['unit_cny']:.5f} |" for q in parts]
(ROOT/'cost/费用说明.md').write_text('\n'.join(lines)+'\n',encoding='utf8')

esc=lambda v:html.escape(str(v))
rows=''.join(f'<tr><td>{esc(k)}</td><td>¥{v:.2f}</td></tr>' for k,v in groups.items())
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板 V5</title><style>
body{margin:0;background:#edf3f5;color:#183b45;font:16px/1.7 "Microsoft YaHei",Arial}main{max-width:1300px;margin:auto;padding:30px}.sub{color:#607c87}h1{font-size:32px;margin:0}h2{font-size:21px}.note{background:#fff0d2;border-radius:12px;padding:16px}.stats{display:flex;gap:14px;flex-wrap:wrap}.stats>div{background:white;border-radius:12px;padding:16px;flex:1;min-width:160px}.stats b{display:block;font-size:24px}.grid{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-top:20px}.card{background:white;border-radius:16px;padding:22px}a,button{color:#006c61}a{margin-right:12px}button{padding:7px 12px;border:1px solid #bdd0d7;background:#fff;border-radius:7px;cursor:pointer}#viewport{overflow:auto;max-height:690px}#pcb{width:100%;min-width:700px}table{width:100%;border-collapse:collapse;font-size:14px}td{padding:9px;border-bottom:1px solid #e0e9ed}.power{background:#eff8f6;border-radius:10px;padding:16px}li{margin:8px 0}@media(max-width:850px){main{padding:16px}.grid{grid-template-columns:1fr}}
</style><main><div class="sub">VOICE INTERCOM · V5 · ENGINEERING REVIEW</div><h1>稳压5V UPS方案主板</h1><p class="sub">ESP32-S3 N8R8＋ML307C-DL · 双层 · 单面SMT · 可选生命体征接口</p>
<p class="note">当前完成UPS接口后的主板设计。中央区域预留真实UPS芯片与配套，尚未完成UPS内部电路，也未生产放行。输出5V采用用户指定假设。</p>
<div class="stats"><div><b>100 × 75 mm</b>两层PCB / 单面SMT</div><div><b>ERC __ERC__ / DRC __DRC__</b>未连接 __GAPS__</div><div><b>¥__MATERIAL__</b>主板材料＋UPS5元额度</div><div><b>¥__ASSEMBLED__</b>含制造额度 / 非工厂报价</div></div>
<div class="grid"><section class="card"><h2>实际布线预览</h2><button onclick="view('front.svg')">正面铜与丝印</button> <button onclick="view('back.svg')">背面铜</button> <button onclick="view('assembly.svg')">器件与预留区</button> <button onclick="zoom(1.2)">放大</button> <button onclick="zoom(.8)">缩小</button><div id="viewport"><img id="pcb" src="front.svg" alt="当前KiCad PCB实际铜层"></div><p><a href="schematic.svg" target="_blank">完整原理图</a><a href="validation.json">检查记录</a><a href="bom.json">逐项BOM</a><a href="voice-v5-review.zip">下载KiCad工程</a></p></section>
<aside class="card"><h2>保留接口</h2><ul><li>5.5/2.5mm圆口，中心正极</li><li>TTL四针：GND / TX43 / RX44 / 5V</li><li>BOOT呼叫、接听键和外部按钮接口</li><li>单声道I2S功放及喇叭接口</li><li>外接INMP441麦克风接口</li><li>雷达可选：5V / GND / RX6 / TX8</li><li>ESP ADC电池采样、外电掉电检测</li><li>USB维修与Host互斥选装</li></ul><p class="sub">主电源供电时TTL的5V线不接。官方ESP通话协议和主动丢旧包逻辑未改。</p></aside></div>
<div class="grid"><section class="card"><h2>新的供电结构</h2><div class="power">圆口 → 保险丝/反接保护 → UPS输入<br>受保护电池 → UPS<br><br><b>UPS稳压5V输出</b><br>→ TPS563201 → 约3.779V → ML307<br>→ SY8089A1 → 约3.315V → ESP32/麦克风<br>→ 直接5V → I2S功放/可选雷达</div><p>4G降压靠近模组，470μF电容放在5V侧。主干预布1.0～1.2mm供电线，信号随后绕行；实际电流能力、压降和温升仍需实测。</p><p class="note">TI PSpice模型在当前ngspice兼容环境中不收敛，未记作仿真通过。独立分压计算、ERC和DRC不能替代UPS切换、电源瞬态、RF/USB与通话实测。</p></section><section class="card"><h2>当前费用与待定项</h2><table>__ROWS__</table><p>制造预算另计¥8.50，主板预算¥__ASSEMBLED__。1000台约¥__TOTAL__。</p><p>SIM暂保留已有图纸的JAE卡座，拿到低价SIM精确焊盘图并通过验收后，条件预算约¥__CHEAP__。</p><p class="sub">UPS实际IC与内部电路待确认；电池、外壳、适配器、喇叭、雷达、外接麦克风和线束不计。当前不能用预留区焊盘当成真实UPS芯片封装下单。</p></section></div>
<p class="sub">C-DL库来源：<b>嘉立创EDA/EasyEDA官方库 / JLCEDA/EasyEDA Official Library</b>。<a href="https://lceda.cn/">嘉立创EDA</a><a href="https://easyeda.com/">EasyEDA</a>TI降压焊盘按厂家DDC0006A推荐图转录。</p></main><script>let factor=1;function view(name){document.getElementById('pcb').src=name}function zoom(v){factor=Math.max(.75,Math.min(4,factor*v));document.getElementById('pcb').style.width=(100*factor)+'%'}</script></html>'''
for key,value in {'__ERC__':status['ERC'],'__DRC__':status['DRC'],'__GAPS__':status['unconnected'],
    '__MATERIAL__':f'{material:.2f}','__ASSEMBLED__':f'{assembled:.2f}','__ROWS__':rows,
    '__TOTAL__':f'{assembled*1000:.2f}','__CHEAP__':f'{assembled-cheap_sim_difference:.2f}'}.items():page=page.replace(key,str(value))
(ROOT/'exports/review.html').write_text(page,encoding='utf8')
bundle=ROOT/'exports/voice-v5-review.zip'
selected=[ROOT/f'voice_mainboard_v5.{ext}' for ext in ['kicad_pcb','kicad_sch','kicad_pro','kicad_dru']]
selected += [ROOT/name for name in ['README.md','design.json','VoiceV2.kicad_sym','fp-lib-table','sym-lib-table']]
selected += list((ROOT/'VoiceV2.pretty').glob('*.kicad_mod'))+list((ROOT/'sources').glob('*.json'))
selected += [ROOT/'cost/bom-budget.json',ROOT/'cost/费用说明.md',ROOT/'exports/validation.json',ROOT/'exports/design-audit.json',ROOT/'exports/modem-buck-model/result.json']
if (ROOT/'cost/3套与5套打样费用核查.md').exists():
    selected.append(ROOT/'cost/3套与5套打样费用核查.md')
    selected += list((ROOT/'cost/sample-3-5').glob('*.json'))
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
    for f in selected:z.write(f,Path('voice_mainboard_v5')/f.relative_to(ROOT))
print(json.dumps({'material':float(material),'assembled':float(assembled),'checks':status,'installed_counts':counts},ensure_ascii=False,indent=2))
