"""Finalize this local stage's audit and preview; not a manufacturing release."""
import json,hashlib,subprocess
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
FILE=ROOT/'voice_mainboard_v7.kicad_pcb'
CLI=ROOT.parents[1]/'build/cad-tools/kicad/bin/kicad-cli.exe'
OUT=ROOT/'exports'
b=p.LoadBoard(str(FILE))
report=json.loads((OUT/'local-layout-validation.json').read_text(encoding='utf-8'))
d=json.loads((OUT/'drc.json').read_text(encoding='utf-8'))
remove={i['uuid']for v in d['violations']if v['type']=='via_dangling'for i in v['items']}
held=[]
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString()in remove:
        report['removed_stubs'].append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'reason':'Unused temporary escape via; route now transitions through other vias'})
        held.append(t);b.Remove(t)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
subprocess.run([str(CLI),'pcb','drc','--schematic-parity','--severity-all','--format','json','-o',str(OUT/'drc.json'),str(FILE)],check=True)
d=json.loads((OUT/'drc.json').read_text(encoding='utf-8'))
assert not d['violations']and not d['unconnected_items']and not d['schematic_parity']
report.update(PCB_sha256=hashlib.sha256(FILE.read_bytes()).hexdigest(),DRC_errors=0,DRC_warnings=0,unconnected=0,schematic_parity=0)
report['original_V6_sha256']=hashlib.sha256((ROOT.parent/'voice_mainboard_v6/voice_mainboard_v6.kicad_pcb').read_bytes()).hexdigest()
# Preserve intermediate route attempts as evidence, distinguish from final state.
report['intermediate_route_attempts']=report.pop('supply_routes',[])
report['final_supply_networks_connected']=True
project=ROOT/'voice_mainboard_v7.kicad_pro'
cfg=json.loads(project.read_text(encoding='utf-8'));cfg['meta']['filename']='voice_mainboard_v7.kicad_pro'
project.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,layers in [('front.svg','F.Cu,F.SilkS,Edge.Cuts'),('back.svg','B.Cu,B.SilkS,Edge.Cuts')]:
    subprocess.run([str(CLI),'pcb','export','svg','--mode-single','--layers',layers,'--page-size-mode','2','-o',str(OUT/name),str(FILE)],check=True,capture_output=True)
(OUT/'local-layout-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板V7工作版</title><style>body{background:#f5f7fa;color:#263b50;font:16px/1.7 'Microsoft YaHei',sans-serif;margin:0}main{max-width:1100px;margin:auto;padding:24px}.note{background:#fff1d0;padding:14px;border-left:4px solid #b68b22}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.grid section{background:white;padding:16px;border:1px solid #dce3eb}img{width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #dce3eb}table{border-collapse:collapse;width:100%;background:white}th{background:#263b50;color:white}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style><main><h1>语音对讲主板V7工作版</h1><p>两层 · 100×75mm · 局部供电布局优化</p><p class="note">本版只完成局部电源与去耦调整。整板重新布局、准确选型及实物验证尚未完成，未生产放行。</p><p>当前原生检查：DRC错误0、警告0、未连接0、原理图连接差异0。</p><table><tr><th>局部修改</th><th>原距离</th><th>现在距离</th></tr><tr><td>功放100nF去耦</td><td>5.63mm</td><td>1.95mm</td></tr><tr><td>充电输入电容</td><td>8.05mm</td><td>2.62mm</td></tr><tr><td>充电电池侧电容</td><td>5.34mm</td><td>3.75mm</td></tr></table><p>距离是焊盘中心直线距离，不是回路电感或实测噪声结论。</p><div class="grid"><section><h2>正面</h2><img src="front.svg"></section><section><h2>背面</h2><img src="back.svg"></section></div><p><a href="../README.md">技术决定与当前进度</a> · <a href="local-layout-validation.json">当前校验记录</a></p></main></html>'''
(OUT/'review.html').write_text(html,encoding='utf-8')
print(json.dumps({k:v for k,v in report.items()if k not in ['removed_stubs','intermediate_route_attempts']},ensure_ascii=False,indent=2))
