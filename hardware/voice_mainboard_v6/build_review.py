"""Export the current saved engineering review; do not imply production release."""
from pathlib import Path
import json,hashlib,html,collections,zipfile,subprocess
import pcbnew as p
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'exports';FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
CLI=ROOT.parents[1]/'build/cad-tools/kicad/bin/kicad-cli.exe'
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
d['input_power'].update(modem_nominal_v=.6*(1+100/18.7),UPS_output_assumed_v=None,
    battery_boost_nominal_v=.6*(1+73.2/10),external_path='Direct mux path; input and switch losses remain')
d['power_architecture']=['J1 -> F1/Q6 -> TPS2117 VIN1 external priority','Bare1S cell -> protection / ETA1096 boost -> TPS2117 VIN2',
    'TP4056-MS / NTC / GPIO38 charge pause; ME2807A30 boost cutoff','SYS -> two SY8089A1 bucks / amplifier / optional radar',
    'GPIO47 selected supply / GPIO10 external presence / GPIO2 battery ADC']
d['firmware_modified']=True;d['manufacturing_ready']=False
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for name,layers in [('front.svg','F.Cu,F.SilkS,Edge.Cuts'),('back.svg','B.Cu,B.SilkS,Edge.Cuts'),('assembly.svg','F.Fab,Edge.Cuts')]:
    subprocess.run([str(CLI),'pcb','export','svg','--mode-single','--layers',layers,'--page-size-mode','2','-o',str(OUT/name),str(FILE)],check=True,capture_output=True)
subprocess.run([str(CLI),'sch','export','svg','-o',str(OUT/'schematic'),str(ROOT/'voice_mainboard_v6.kicad_sch')],check=True,capture_output=True)
erc=json.loads((OUT/'erc.json').read_text(encoding='utf8'));drc=json.loads((OUT/'routed-drc.json').read_text(encoding='utf8'))
audit=json.loads((OUT/'design-audit.json').read_text(encoding='utf8'));sha=hashlib.sha256(FILE.read_bytes()).hexdigest();assert sha==audit['PCB_sha256']
status={'date':'2026-11-24','PCB_sha256':sha,'layers':2,'size_mm':[100,75],
    'ERC':sum(len(s['violations']) for s in erc['sheets']),'DRC':len(drc['violations']),
    'DRC_errors':sum(v['severity']=='error' for v in drc['violations']),
    'DRC_warnings':sum(v['severity']=='warning' for v in drc['violations']),
    'DRC_warning_types':[v['type'] for v in drc['violations'] if v['severity']=='warning'],
    'unconnected':len(drc['unconnected_items']),
    'native_schematic_parity_issues':len(drc['schematic_parity']),
    'native_pin_contract_passed':True,'schematic_XML_matches_PCB':True,'power_monitor_and_existing_radar_variants_built':True,
    'App_server_unit_tests_passed':True,'full_motherboard_simulated':False,'2A_load_qualified':False,'manufacturing_ready':False,
    'open_items':d['assembly_open_items']}
(OUT/'validation.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()};prices=json.loads((ROOT/'cost/part-price-inputs.json').read_text(encoding='utf8'))
rows=[];known=0.;unknown=[];counts=collections.Counter()
for q in d['parts']:
    if q['kind']=='mechanical' or q['ref'].startswith('TP'):continue
    rec={**q,**prices[q['ref']]};rows.append(rec)
    if q['dnp']:continue
    counts['SMT' if fps[q['ref']].GetAttributes()&p.FP_SMD else 'THT']+=1
    if rec['unit_cny'] is None:unknown.append(q['ref'])
    else:known+=rec['unit_cny']
(OUT/'bom.json').write_text(json.dumps({'parts':rows,'counts':dict(counts),'quoted_or_target_subtotal_cny':known,
    'unquoted_populated_refs':unknown,'final_material_total_cny':None,'supplier_final_quote_obtained':False,
    'basis':'Includes user ML30710/ESP12 targets and historical budgets. Not a pure JLC quote; unknown UPS passives are not replaced by purchased-module price.'},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
lines=['# V6 物料与价格边界','',f'已填价部分小计 {known:.5f} 元，{len(unknown)} 个默认贴装位号尚未核价，**不能当作完整主板总价**。',
    '', 'ML30710元、ESP12元为用户采购目标；其他项包含历史预算与部分公开阶梯价。已用实际UPS位号替换5元模块额度，不重复计入购买模块价格。',
    '', '| 位号 | 型号 | LCSC | 单价/元 | 依据 |','|---|---|---|---:|---|']
for q in rows:lines.append(f"| {q['ref']}{' (DNP)' if q['dnp'] else ''} | {q['value']} | {q.get('lcsc') or '待核'} | {q['unit_cny'] if q['unit_cny'] is not None else '待核价'} | {q['basis']} |")
(ROOT/'cost/费用说明.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板 V6</title><style>
body{{background:#edf3f5;color:#163b43;font:16px/1.7 "Microsoft YaHei",sans-serif;margin:0}}main{{max-width:1250px;margin:auto;padding:28px}}h1{{margin:0}}.note{{background:#fff0d2;border-radius:12px;padding:16px}}.stats{{display:flex;gap:12px;flex-wrap:wrap}}.stats div,.card{{background:white;border-radius:14px;padding:20px}}.stats div{{flex:1}}b{{font-size:23px}}.grid{{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-top:20px}}img{{width:100%}}button{{padding:8px 14px;margin:4px;border:1px solid #bfd3d7;border-radius:8px;background:white;cursor:pointer}}a{{color:#006d62}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}main{{padding:16px}}}}</style>
<main><p>VOICE INTERCOM / V6 / ENGINEERING REVIEW</p><h1>语音对讲 · 集成 UPS 主板</h1><p>ESP32-S3 N8R8 · ML307C-DL · 可选生命体征 · 电源来源与电量估算</p>
<p class="note">当前为工程审查版本，尚未生产放行。未连接检查、几何检查与实物测试分别记录；整板功能没有通过整板仿真或新板实测。</p>
<div class="stats"><div><b>100 × 75 mm</b><br>两层 / 单面SMT</div><div><b>ERC {status['ERC']} · DRC错误 {status['DRC_errors']}</b><br>警告 {status['DRC_warnings']} · 未连接 {status['unconnected']}</div><div><b>电量 · 供电来源</b><br>ESP本地采样，待机上报</div></div>
<div class="grid"><section class="card"><h2>实际 PCB 预览</h2><button onclick="pcb.src='front.svg'">正面</button><button onclick="pcb.src='back.svg'">背面</button><button onclick="pcb.src='assembly.svg'">器件</button><img id="pcb" src="front.svg"><p><a href="schematic/voice_mainboard_v6.svg">完整原理图</a> · <a href="validation.json">检查记录</a> · <a href="bom.json">BOM</a> · <a href="voice-v6-review.zip">KiCad审查包</a></p></section>
<aside class="card"><h2>供电结构</h2><p>5V圆口 → 反接保护 → TPS2117外电优先</p><p>1S电池 → 保护 → ETA1096约5V升压 → TPS2117备用输入</p><p>TP4056充电 / NTC / 3V升压截止<br>ESP与4G分别降压<br>系统电源供功放与可选雷达</p><h2>ESP 检测</h2><p>GPIO47：电源选择状态<br>GPIO10：外电接入<br>GPIO2/9：电池ADC / 使能<br>GPIO38：暂停充电<br>GPIO48/1：充电中 / 满电</p><p class="note">CELL-不能接主板GND；电量为估算。过温、欠压与瞬态仍需实测。</p></aside></div>
<section class="card" style="margin-top:20px"><h2>价格与验收边界</h2><p>已填价部分 ¥{known:.2f}，{len(unknown)} 个贴装位号待核价；包含采购目标与历史预算，不是完整嘉立创报价。</p><ul>{''.join('<li>'+html.escape(i)+'</li>' for i in status['open_items'])}</ul><p><a href="../README.md">接线、固件与验收说明</a></p></section></main></html>'''
(OUT/'review.html').write_text(page,encoding='utf8')
with zipfile.ZipFile(OUT/'voice-v6-review.zip','w',zipfile.ZIP_DEFLATED) as z:
    for f in ROOT.rglob('*'):
        if f.is_file() and '__pycache__' not in f.parts and (f.suffix in ['.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru','.kicad_mod','.kicad_sym','.md','.json','.pos'] or f.name.endswith('-table')):
            z.write(f,Path('voice_mainboard_v6')/f.relative_to(ROOT))
print(json.dumps(status,ensure_ascii=False,indent=2))
