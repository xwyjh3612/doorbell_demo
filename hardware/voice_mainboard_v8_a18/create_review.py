"""Build a local review page and a true-size mechanical template from CAD data."""
from pathlib import Path
import datetime, hashlib, html, json, os
ROOT=Path(__file__).resolve().parent
FILE=Path(os.environ.get('A18_AUDIT_BOARD',str(ROOT/'voice_mainboard_v8_a18.kicad_pcb'))).resolve()
ROOT=FILE.parent;OUT=ROOT/'exports'
design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
drc=json.loads((OUT/'review-drc.json').read_text(encoding='utf-8'))
electrical=json.loads((OUT/'electrical-audit/results.json').read_text(encoding='utf-8'))
control=json.loads((OUT/'simulation/results.json').read_text(encoding='utf-8'))
copper=json.loads((OUT/'copper-path-audit.json').read_text(encoding='utf-8'))if (OUT/'copper-path-audit.json').exists()else None
widths=json.loads((OUT/'power-width-audit.json').read_text(encoding='utf-8'))if (OUT/'power-width-audit.json').exists()else None
erc=json.loads((OUT/'erc.json').read_text(encoding='utf-8'))
erc_count=sum(len(s['violations'])for s in erc.get('sheets',[]))
sha=hashlib.sha256(FILE.read_bytes()).hexdigest()
assert electrical['PCB_sha256']==sha and control['PCB_sha256']==sha,'Re-run audits for this exact saved PCB'
assert electrical['schematic_sha256']==control['schematic_sha256']==hashlib.sha256(FILE.with_suffix('.kicad_sch').read_bytes()).hexdigest()
assert drc['source']==FILE.name,'DRC is for a different PCB'
counts={k:len(drc.get(k,[]))for k in ['violations','schematic_parity','unconnected_items']}
template=['<svg xmlns="http://www.w3.org/2000/svg" width="93mm" height="109mm" viewBox="-10 -13 93 109">',
 '<rect x="-10" y="-13" width="93" height="109" fill="white"/>',
 '<style>text{font-family:Arial,sans-serif;font-size:2.2px} .outline{fill:none;stroke:#111;stroke-width:.15} .guide{fill:none;stroke:#777;stroke-width:.1;stroke-dasharray:1 1}</style>',
 '<text x="0" y="-9">A18 / 73 x 73 mm / PCB mechanical candidate</text>',
 '<text x="0" y="-5">PRINT AT 100% / no fit-to-page; dimensions need shell verification</text>',
 '<polygon class="outline" points="'+' '.join(f'{x},{y}'for x,y in design['mechanical']['outline_mm'])+'"/>']
for x,y in design['mechanical']['mount_holes_mm']:
    template.extend([f'<circle class="outline" cx="{x}" cy="{y}" r="1.5"/>',
                     f'<circle class="guide" cx="{x}" cy="{y}" r="3.5"/>',
                     f'<path class="guide" d="M {x-2} {y} h 4 M {x} {y-2} v 4"/>'])
jack=next(q for q in design['parts'] if q['ref']=='J1')
jack_recess=None
if design['layers']==2 and jack['side']=='B' and abs(jack['angle']%360-180)<.001:
    jack_x,jack_y=jack['x'],jack['y']
    assumed_wall_x=(85+design['dimensions_mm'][0])/2
    jack_recess=assumed_wall_x-jack_x
    template.extend([f'<rect class="guide" x="{jack_x-14.2}" y="{jack_y-5.5}" width="14.2" height="11"/>',
                     f'<path class="guide" d="M {jack_x} {jack_y} H {assumed_wall_x} m 0 -7 v 14"/>',
                     f'<text x="{jack_x-15}" y="{jack_y+8}">J1 BACK / VERIFY PLUG</text>'])
template.extend(['<rect class="guide" x="30" y="30" width="13" height="13"/>',
 '<circle class="outline" cx="36.5" cy="36.5" r="1"/>',
 '<circle class="guide" cx="36.5" cy="9.9" r="1.5"/>',
 '<text x="29" y="47">CALL BUTTON</text>',
 '<text x="26" y="64">BATTERY CLEARANCE</text>',
 '<path class="outline" d="M 0 83 h 50 M 0 81 v 4 M 50 81 v 4"/>',
 '<text x="18" y="87">50 mm CHECK SCALE</text>',
 '<text x="0" y="93">4 holes: diameter 3 mm / centres 66 x 66 mm</text></svg>'])
(OUT/'mechanical-1to1.svg').write_text('\n'.join(template),encoding='utf-8')
rows=''.join(f'<tr><td>{html.escape(net)}</td><td>{q["nominal_V"]:.3f} V</td><td>{q["min_V"]:.3f}–{q["max_V"]:.3f} V</td></tr>'for net,q in electrical['voltage_corners'].items())
status=f'ERC {erc_count} · DRC {counts["violations"]} · 未连接 {counts["unconnected_items"]} · 原理图一致性 {counts["schematic_parity"]}'
cases=''.join(f'<tr><td>{q["case"]}</td><td>{q["TEMP_VCC_ratio"]:.3f}</td><td>{"允许"if q["charge_allowed_by_nominal_TEMP"]else"暂停"}</td></tr>'for q in control['cases'])
traces=json.loads((OUT/'electrical-audit/sampled-traces.json').read_text(encoding='utf-8'))
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板 · A18设计审查</title>
<style>body{margin:0;background:#eef3f5;color:#182f3c;font:16px/1.6 "Microsoft YaHei",sans-serif}main{max-width:1120px;margin:40px auto;padding:0 22px}h1{font-size:30px;margin:0}h2{font-size:21px;margin-top:0}p{margin:10px 0}.muted{color:#556e7b}.pill{display:inline-block;padding:6px 12px;border-radius:8px;background:#ffedc2;color:#705415}section{background:white;padding:24px;border-radius:16px;margin:20px 0;box-shadow:0 3px 20px #1937480b}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.board{width:100%;background:#111;max-height:730px;object-fit:contain}button,a{color:#086078}button{padding:8px 17px;background:#e7f4f4;border:1px solid #b5d4d7;border-radius:8px;cursor:pointer;margin:0 8px 12px 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:9px;border-bottom:1px solid #dce5e9}canvas{width:100%;height:280px;border:1px solid #dde5e8;border-radius:8px}code{font-size:11px;overflow-wrap:anywhere}@media(max-width:750px){.grid{grid-template-columns:1fr}main{margin:20px auto}section{padding:17px}}</style>
<main><p class="muted">A18外壳 · 两层板 · 双面贴装 · 73×73 mm异形轮廓</p><h1>语音对讲主板</h1><p>设计审查版，尚未生产放行。</p><p class="pill">__STATUS__</p>
<section><h2>实际PCB预览</h2><button onclick="show('front')">正面</button><button onclick="show('back')">背面</button><img class="board" id="board" src="review-front.png"><p class="muted">来自当前KiCad工程的铜层与器件图。下方缺口避让电池仓；四角保留安装孔，中央为呼叫键，上方为RGB灯。背面显示采用镜像视图。</p></section>
<div class="grid"><section><h2>反馈电压与引脚核查</h2><p>已核对 __PINS__ 个已连接引脚；PCB与原理图网表一致。</p><table><tr><th>电源</th><th>名义值</th><th>反馈与阻值容差</th></tr>__ROWS__</table><p class="muted">以上是反馈工作点计算，未包含负载动态压降。</p></section>
<section><h2>充电控制仿真</h2><p>ngspice实际运行：电阻分压、理想CE开关。充电设定100mA，NTC暂按10k/B3950。</p><table><tr><th>工况</th><th>TEMP/VCC</th><th>名义判断</th></tr>__CASES__</table><p class="muted">80%停充/70%再充尚未实现；NTC短接到地可能禁用芯片温度监测，不能据开路测试宣称短路受保护。</p></section></div>
<section><h2>断电切换的储能敏感性</h2><p>下图为实际ngspice波形：理想电源中断、2A负载、输入4.5V，包含C8储能与假定的电容有效值/线路电阻。5µs与100µs是扫描条件，不能当作芯片保证值。</p><canvas id="plot" width="1000" height="280"></canvas><p class="muted">模拟可发现储能不足的敏感条件；没有实际升降压、切换芯片内部模型，不能据此宣布UPS峰值、热性能和整板已通过。</p></section>
<section><h2>装壳核对与文件</h2><p><a href="mechanical-1to1.svg">下载1:1机械模板</a> · <a href="voice-mainboard-board-only.step">板体STEP</a> · <a href="voice-mainboard-models.step">含已有器件模型的STEP</a> · <a href="../voice_mainboard_v8_a18.kicad_pcb">KiCad PCB</a> · <a href="../voice_mainboard_v8_a18.kicad_sch">原理图</a></p><p>模板按100%打印，先确认50mm标尺，再核对实物外壳。尚需确认螺柱外径、缺口、按钮行程、导光柱，以及电池、喇叭和插头线弯折空间。STEP中缺失的器件模型不代表器件不存在。</p><p><a href="review-drc.json">原生DRC记录</a> · <a href="electrical-audit/results.json">电气核查与12组动态模型结果</a> · <a href="simulation/results.json">4组控制仿真结果</a></p><p class="muted">PCB SHA256 <code>__SHA__</code><br>生成时间 __DATE__</p></section></main>
<script>function show(side){document.getElementById('board').src='review-'+side+'.png'}const traces=__TRACES__;const c=document.getElementById('plot'),g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,c.width,c.height);const x=t=>55+(t-.85)/.5*910,y=v=>225-(v-3.3)/1.1*190;g.font='13px Arial';g.strokeStyle='#dae3e9';for(let v=3.4;v<=4.5;v+=.2){g.beginPath();g.moveTo(55,y(v));g.lineTo(970,y(v));g.stroke();g.fillStyle='#415c6d';g.fillText(v.toFixed(1)+'V',8,y(v)+4)}for(let i=0;i<traces.length;i++){g.strokeStyle=['#087e8b','#c97421'][i];g.lineWidth=2;g.beginPath();let started=false;traces[i].time_ms.forEach((t,j)=>{if(t<.85||t>1.35)return;if(!started){g.moveTo(x(t),y(traces[i].SYS_V[j]));started=true}else g.lineTo(x(t),y(traces[i].SYS_V[j]))});g.stroke();g.fillStyle=g.strokeStyle;g.fillText(traces[i].case,70+410*i,260)}g.fillStyle='#415c6d';g.fillText('1.00 ms: assumed source interruption',60,18)</script></html>'''
for key,value in {'STATUS':status,'PINS':str(electrical['connected_pins_checked']),'ROWS':rows,'CASES':cases,'SHA':sha,
                  'DATE':datetime.datetime.now().astimezone().isoformat(),'TRACES':json.dumps(traces,separators=(',',':'))}.items():
    page=page.replace('__'+key+'__',value)
storage_report=OUT/'vbat-storage/results.json'
if storage_report.exists():
    storage=json.loads(storage_report.read_text(encoding='utf-8'))
    assert storage['PCB_sha256']==sha
    cases={q['assumed_source_interruption_us']:q['minimum_VBAT_V'] for q in storage['cases'] if q['with_C75_C76']}
    storage_section=(f'<section><h2>4G 模组电源储能</h2><p>保留两颗22µF陶瓷电容，在模组3.8V输入附近增设C75/C76，各220µF。'
        f'假设稳压源中断且负载需求升到2A，模型中断50µs时最低{cases[50]:.3f}V，100µs时最低{cases[100]:.3f}V；模组VBAT下限为3.4V。</p>'
        '<p>模拟假设地回流理想，未包含稳压器启动、限流和环路稳定性。新板须在模组脚处实测发射电压与启动波形。'
        '<a href="vbat-storage/results.json">模型和完整结果</a></p></section>')
    page=page.replace('<section><h2>装壳核对与文件</h2>',storage_section+'<section><h2>装壳核对与文件</h2>')
page=page.replace('两层板',('两层板' if design['layers']==2 else '四层布线对照（未选为生产方案）'))
page=page.replace('../voice_mainboard_v8_a18.kicad_pcb','../'+FILE.name).replace('../voice_mainboard_v8_a18.kicad_sch','../'+FILE.with_suffix('.kicad_sch').name)
page=page.replace('来自当前KiCad工程的铜层与器件图。','来自当前KiCad工程的铜层与器件图。红／绿是铜层显示颜色，实际阻焊颜色可在下单时选择。')
if jack_recess is not None:
    page=page.replace('以及电池、喇叭和插头线弯折空间。',f'以及电池、喇叭和插头线弯折空间。圆口放在背面；按外壳和PCB居中估算，插座口距外壁约{jack_recess:.2f}mm。需用实际插头核对开孔和插入深度。')
if copper:
    assert copper['PCB_sha256']==sha
    pathrows=''.join('<tr><td>'+html.escape(q['net'])+'</td><td>'+html.escape(str(q['from'])+' → '+str(q['to']))+'</td><td>'+f'{q["centreline_length_mm"]:.1f} mm</td><td>'+f'{q["estimated_drop_at_2A_V"]:.3f} V</td></tr>'for q in copper['paths']if q['trace_graph_connected']and q['net']!='MODEM_RESET_N')
    supply='<section><h2>实际铜路径估算</h2><table><tr><th>电源</th><th>起点 → 终点</th><th>路径</th><th>假设2A时压降</th></tr>'+pathrows+'</table><p class="muted">由当前走线和过孔计算；假定铜厚35µm、孔铜20µm、20℃。不含芯片、接点、电感及电池内阻，也不是2A温升或峰值认证。</p><p>仍需完成射频与USB阻抗/参考地审查、开关电源回路审查、电芯与NTC、L5型号及装壳核验。复位线的当前长度仍需按模组手册复核。</p></section>'
    if widths:
        assert widths['PCB_sha256']==sha
        narrow_count=sum(len(q['long_narrow_segments'])for q in widths['rails'])
        supply=supply.replace('</section>',f'<p>当前有{narrow_count}段电源铜线超过1.5mm且小于0.5mm宽（含支路和悬空段），仍需结合实际电流路径调整。连续短段也可能形成长颈线。</p><p><a href="power-width-audit.json">逐段电源线宽审查</a> · <a href="copper-path-audit.json">铜路径计算依据</a></p></section>')
    page=page.replace('<section><h2>装壳核对与文件</h2>',supply+'<section><h2>装壳核对与文件</h2>')
for name,label in [('voice-mainboard-board-only.step','板体STEP'),('voice-mainboard-models.step','含已有器件模型的STEP')]:
    if not (OUT/name).exists():
        page=page.replace(f' · <a href="{name}">{label}</a>','')
(OUT/'preview.html').write_text(page,encoding='utf-8')
review={'PCB_sha256':sha,'native_DRC_counts':counts,'mechanical_fit_verified':False,'full_board_simulated':False,
        'manufacturing_ready':False,'firmware_modified':False,'review_page':'exports/preview.html','copper_layers':design['layers'],
        'ERC_violations':erc_count,
        'review_scope':'Native CAD connectivity and explicitly scoped subcircuit models; 2A and assembled-board function not qualified'}
(OUT/'review-summary.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
print(status)
