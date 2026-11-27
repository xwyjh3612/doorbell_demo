"""Check and package the isolated layout candidate, leaving V6 untouched."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
import pcbnew as p

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
WORK=REPO/'build/v6-layout-refinement-20261124'
CANDIDATE=WORK/'candidate'
PCB=CANDIDATE/'voice_mainboard_v6.kicad_pcb'
CLI=REPO/'build/cad-tools/kicad/bin/kicad-cli.exe'
OUT=ROOT/'exports/engineering-review-20261124'
OUT.mkdir(parents=True,exist_ok=True)
report=json.loads((WORK/'candidate-changes.json').read_text(encoding='utf-8'))
cleanup_history=WORK/'terminal-stub-cleanup.json'
removed=json.loads(cleanup_history.read_text(encoding='utf-8')) if cleanup_history.exists() else []
for attempt in range(3):
    drc=json.loads((WORK/'candidate-drc.json').read_text(encoding='utf-8'))
    dangling={i['uuid'] for v in drc['violations'] if v['type']=='track_dangling' and v['severity']=='warning' for i in v['items']}
    if not dangling:break
    b=p.LoadBoard(str(PCB));held=[]
    for t in list(b.GetTracks()):
        if t.m_Uuid.AsString() in dangling:
            removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'reason':'Native DRC identified unconnected terminal stub'})
            held.append(t);b.Remove(t)
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(PCB),b)
    for t in held:t.thisown=False
    subprocess.run([str(CLI),'pcb','drc','--schematic-parity','--severity-all','--format','json','-o',str(WORK/'candidate-drc.json'),str(PCB)],check=True)

drc=json.loads((WORK/'candidate-drc.json').read_text(encoding='utf-8'))
assert not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity'],drc
report.update(candidate_PCB_sha256=hashlib.sha256(PCB.read_bytes()).hexdigest(),removed_terminal_stubs=removed,
              DRC_errors=0,DRC_warnings=0,unconnected=0,native_schematic_parity=0)
report['2A_qualified']=False
(cleanup_history).write_text(json.dumps(removed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
counts={'horizontal_vertical':0,'45_degree':0,'arbitrary_angle':0}
board=p.LoadBoard(str(PCB))
for t in board.GetTracks():
    if isinstance(t,p.PCB_VIA):continue
    a,z=t.GetStart(),t.GetEnd();dx,dy=abs(a.x-z.x),abs(a.y-z.y)
    if min(dx,dy)<20:counts['horizontal_vertical']+=1
    elif abs(dx-dy)<20:counts['45_degree']+=1
    else:counts['arbitrary_angle']+=1
report['angle_after']=counts
report['original_unchanged']=hashlib.sha256((ROOT/'voice_mainboard_v6.kicad_pcb').read_bytes()).hexdigest()==report['base_PCB_sha256']
assert report['original_unchanged']
for name,layers in [('candidate-front.svg','F.Cu,F.SilkS,Edge.Cuts'),('candidate-back.svg','B.Cu,B.SilkS,Edge.Cuts')]:
    subprocess.run([str(CLI),'pcb','export','svg','--mode-single','--layers',layers,'--page-size-mode','2','-o',str(OUT/name),str(PCB)],check=True,capture_output=True)
shutil.copy2(ROOT/'exports/front.svg',OUT/'original-front.svg')
shutil.copy2(ROOT/'exports/back.svg',OUT/'original-back.svg')
shutil.copy2(WORK/'candidate-drc.json',OUT/'candidate-drc.json')
(OUT/'candidate-changes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with zipfile.ZipFile(OUT/'语音对讲主板走线优化候选.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for f in CANDIDATE.rglob('*'):
        if f.is_file() and f.suffix not in ['.svg']:
            archive.write(f,Path('layout_candidate')/f.relative_to(CANDIDATE))
    archive.write(OUT/'candidate-changes.json','layout_candidate/检查与修改.json')
    archive.write(OUT/'candidate-drc.json','layout_candidate/DRC.json')
    archive.writestr('layout_candidate/README.md','# 语音对讲主板走线优化候选\n\n本包保留原理图与器件布局，仅优化部分走线和主输入供电。\n最终DRC错误0、警告0、未连接0、原理图连接差异0。\n整板电气/热/USB/RF/充电温度/制造工艺尚未全部验证，未生产放行。\n完整审查见项目 hardware/voice_mainboard_v6/整板工程审查与优化建议.md。\n')

html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板 · 工程审查与走线对比</title>
<style>body{margin:0;background:#f4f6f8;color:#25364a;font:16px/1.7 'Microsoft YaHei',sans-serif}main{max-width:1300px;margin:auto;padding:24px}h1{font-size:28px}h2{font-size:20px}.note{padding:14px;background:#fff3d6;border-left:4px solid #b58016}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.card{padding:18px;background:white;border:1px solid #dce3eb;border-radius:8px}.card img{width:100%;background:white}.stats{display:flex;gap:18px;flex-wrap:wrap;margin:20px 0}.stats span{padding:12px 20px;background:white;border:1px solid #dce3eb}button{padding:9px 18px;background:white;border:1px solid #8b9bb0;cursor:pointer;margin:0 8px 16px 0}table{width:100%;border-collapse:collapse;background:white}th,td{padding:12px;text-align:left;border-bottom:1px solid #dde4ed}th{background:#25364a;color:white}a{color:#136ca3}@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:14px}table{font-size:13px}}</style>
<main><h1>语音对讲主板 · 工程审查与走线对比</h1><p>2026-11-24｜100 × 75 mm｜两层板｜审查版</p>
<p class="note">当前候选只修正了部分走线和主输入供电瓶颈，尚未完成器件重新布局。DRC通过不代表整板功能、USB阻抗、2A温升与充电安全已经验证。请勿直接下单生产。</p>
<div class="stats"><span>随意角度走线<br><b>1266 → 185 段</b></span><span>横平竖直与45°路线统一<br><b>1083段重新调整</b></span><span>候选原生DRC<br><b>错误0 · 警告0 · 未连接0</b></span><span>原理图连接一致性<br><b>0个差异</b></span></div>
<button onclick="setLayer('front')">查看正面</button><button onclick="setLayer('back')">查看背面</button>
<div class="grid"><section class="card"><h2>原V6</h2><img id="original" src="original-front.svg"><p>存在大量随意角度；主输入细线；功能与功率验证未完成。</p></section><section class="card"><h2>走线优化候选</h2><img id="candidate" src="candidate-front.svg"><p>减少随意斜线，合并164处共线碎段；主输入改为背面铺铜，0.5/0.6mm短引出与0.8/0.4mm过孔。</p></section></div>
<h2>整板审查发现</h2><table><tr><th>优先级</th><th>位置</th><th>证据与处理</th></tr>
<tr><td>必须修</td><td>主电源路径</td><td>原F1到Q6约18.9mm、0.2mm宽且无分担铺铜；本候选已修这段，整条输入/系统/电池回路仍需验收。</td></tr>
<tr><td>必须确认</td><td>电池温度窗口</td><td>按10k/B3950计算，原分压约−7～38.5℃；必须以电芯充电温度范围重新选阻值。</td></tr>
<tr><td>必须重排</td><td>电源与功放去耦</td><td>充电输入电容距引脚约8.05mm；功放100nF距电源脚约5.63mm；UPS部分电容离芯片较远，不能用连通性代替回路审查。</td></tr>
<tr><td>USB启用前必须重布</td><td>ESP/4G USB预留</td><td>ESP D+ / D−同网铜线累计约145.75 / 185.52mm、13 / 8个过孔；该预留还未形成合格差分线路。</td></tr>
<tr><td>必须核查</td><td>4G降压与UPS峰值</td><td>V6已更换降压芯片，V5 TI模型结果不适用；低电池2A负载的输入电流约3.7A，必须核电芯、保护、连接器和电源环路。</td></tr>
<tr><td>优化成本</td><td>SIM座、小料与接口</td><td>当前JAE卡座2.51元；已有0.4717元国产候选，必须核对焊盘/引脚。常用电容/排针预算仍有进一步压缩空间。</td></tr>
<tr><td>重新分区</td><td>主控、音频、4G、UPS</td><td>功放与ESP距离约80mm，导致I2S绕行；下一次器件布局应缩短音频线，保持4G射频区与开关电源区分离。</td></tr></table>
<p><a href="../../整板工程审查与优化建议.md">完整审查记录</a> · <a href="语音对讲主板走线优化候选.zip">下载KiCad优化候选</a> · <a href="candidate-drc.json">候选DRC记录</a></p>
</main><script>function setLayer(layer){document.getElementById('original').src='original-'+layer+'.svg';document.getElementById('candidate').src='candidate-'+layer+'.svg'}</script></html>'''
(OUT/'走线对比.html').write_text(html,encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='segment_changes'},ensure_ascii=False,indent=2))
