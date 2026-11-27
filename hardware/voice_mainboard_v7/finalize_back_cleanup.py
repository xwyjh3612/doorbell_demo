"""Promote a checked route revision; retain baseline, regenerate audit/preview."""
import collections,hashlib,json,shutil,subprocess
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
WORK=REPO/'build/v7-back-routes-20261124'
FILE=ROOT/'voice_mainboard_v7.kicad_pcb'
OUT=ROOT/'exports';OUT.mkdir(exist_ok=True)
HISTORY=ROOT/'history/20261124-before-back-cleanup'
HISTORY.mkdir(parents=True,exist_ok=True)
CLI=REPO/'build/cad-tools/kicad/bin/kicad-cli.exe'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
change=json.loads((WORK/'route-changes.json').read_text(encoding='utf-8'))
BASE=HISTORY/FILE.name
if not BASE.exists():
    assert sha(FILE)==change['base_sha256']
    for name in [FILE.name,'voice_mainboard_v7.kicad_sch','voice_mainboard_v7.kicad_pro','voice_mainboard_v7.kicad_dru']:
        shutil.copy2(ROOT/name,HISTORY/name)
    shutil.copy2(OUT/'local-layout-validation.json',HISTORY/'local-layout-validation.json')
assert sha(BASE)==change['base_sha256']
def signature(board):
    return sorted((fp.GetReference(),pd.GetNumber(),pd.GetNetname(),pd.GetPosition().x,pd.GetPosition().y)for fp in board.GetFootprints()for pd in fp.Pads())
before=p.LoadBoard(str(BASE));after=p.LoadBoard(str(WORK/FILE.name))
assert signature(before)==signature(after),'Footprint/pad connectivity or placement changed'
frozen={'CELL_NEG','VIN_FUSED','RF_ANT','RF_FEED','M_USB_DP','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19','SERVICE_USB_DP','SERVICE_USB_DM','BUCK_SW','UPS_SW','ESP_SW'}
def copper_signature(board):
    result=[]
    for t in board.GetTracks():
        if t.GetNetname()not in frozen:continue
        if isinstance(t,p.PCB_VIA):result.append((t.GetNetname(),'via',t.GetPosition().x,t.GetPosition().y,t.GetWidth(p.F_Cu),t.GetDrill()))
        else:
            ends=sorted([(t.GetStart().x,t.GetStart().y),(t.GetEnd().x,t.GetEnd().y)])
            result.append((t.GetNetname(),'track',t.GetLayer(),*ends[0],*ends[1],t.GetWidth()))
    return sorted(result)
assert copper_signature(before)==copper_signature(after),'Frozen USB/RF/switch/input/cell-return copper changed'
assert sha(ROOT/'voice_mainboard_v7.kicad_sch')==sha(HISTORY/'voice_mainboard_v7.kicad_sch')
dr=json.loads((WORK/'final-drc.json').read_text(encoding='utf-8'))
assert not dr['violations']and not dr['unconnected_items']and not dr['schematic_parity']
shutil.copy2(WORK/FILE.name,FILE)
subprocess.run([str(CLI),'pcb','drc','--schematic-parity','--severity-all','--format','json','-o',str(OUT/'drc.json'),str(FILE)],check=True)
d=json.loads((OUT/'drc.json').read_text(encoding='utf-8'))
assert not d['violations']and not d['unconnected_items']and not d['schematic_parity']
def xy(v):return p.ToMM(v.x),p.ToMM(v.y)
def stats(b):
    result={}
    for layer in [p.F_Cu,p.B_Cu]:
        tracks=[t for t in b.GetTracks()if not isinstance(t,p.PCB_VIA)and t.GetLayer()==layer]
        joints=collections.defaultdict(list)
        for t in tracks:
            for pt in [t.GetStart(),t.GetEnd()]:joints[(t.GetNetname(),pt.x,pt.y)].append(t)
        bends=0
        for ts in joints.values():
            if len(ts)!=2:continue
            a,z=ts;v=a.GetEnd()-a.GetStart();w=z.GetEnd()-z.GetStart()
            if v.x*w.y!=v.y*w.x:bends+=1
        result[b.GetLayerName(layer)]={'segments':len(tracks),'degree_two_turns':bends,'length_mm':round(sum(p.ToMM(t.GetLength())for t in tracks),3),'ground_segments':sum(t.GetNetname()=='GND'for t in tracks)}
    result['vias']=sum(isinstance(t,p.PCB_VIA)for t in b.GetTracks())
    return result
before_stats=stats(before);after_stats=stats(after)
ground_components=json.loads((WORK/'ground-components.json').read_text(encoding='utf-8'))
assert len(ground_components)==1
report={'date':'2026-11-24','PCB_sha256':sha(FILE),'base_PCB_sha256':sha(BASE),'DRC_errors':0,'DRC_warnings':0,'unconnected':0,'schematic_parity':0,'before':before_stats,'after':after_stats,'ground_geometric_components':1,'ground_audit_method':'Native filled copper polygons including holes + pads + traces + through-vias, union of touching same-layer copper and vertical via/THT connections; corroborated by native DRC. This is connectivity only.','footprint_positions_and_pad_nets_unchanged':True,'schematic_unchanged':True,'changed_footprint_count':0,'added_ground_vias':2,'local_power_returns_preserved':True,'CELL_NEG_unchanged':True,'USB_RF_switch_nodes_unchanged':True,'manufacturing_ready':False,'2A_qualified':False,'full_board_relayout_completed':False,'remaining_scope':['Full placement and USB/RF qualification','Exact BOM/footprints/stock/SMT-library and thermal qualification','Cell/NTC window','2A peak, low-battery takeover and long-call hardware tests'],'evidence':['back-route-changes.json','ground-route-changes.json','ground-return-changes.json','ground-components.json','drc.json']}
(OUT/'back-cleanup-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for src,dest in [('route-changes.json','back-route-changes.json'),('ground-changes.json','ground-route-changes.json'),('ground-return-changes.json','ground-return-changes.json'),('ground-components.json','ground-components.json')]:shutil.copy2(WORK/src,OUT/dest)
previous=json.loads((OUT/'local-layout-validation.json').read_text(encoding='utf-8'))
previous.update(PCB_sha256=sha(FILE),DRC_errors=0,DRC_warnings=0,unconnected=0,schematic_parity=0,back_cleanup_validation='back-cleanup-validation.json')
(OUT/'local-layout-validation.json').write_text(json.dumps(previous,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,layers,path,mirror in [('front.svg','F.Cu,F.SilkS,Edge.Cuts',FILE,False),('back.svg','B.Cu,B.SilkS,Edge.Cuts',FILE,True),('back-before.svg','B.Cu,B.SilkS,Edge.Cuts',BASE,True)]:
    args=[str(CLI),'pcb','export','svg','--mode-single','--exclude-drawing-sheet','--layers',layers,'--page-size-mode','2','-o',str(OUT/name)]
    if mirror:args.append('--mirror')
    subprocess.run(args+[str(path)],check=True,capture_output=True)
# Separate plot copies contain no zones: this view exposes route complexity.
# They stay under build and are never offered as manufacturing files.
for label,path in [('before',BASE),('after',FILE)]:
    board=p.LoadBoard(str(path));held=[]
    for z in list(board.Zones()):
        if not z.GetIsRuleArea():held.append(z);board.Remove(z)
    plot=WORK/f'plot-only-{label}.kicad_pcb';p.SaveBoard(str(plot),board)
    for z in held:z.thisown=False
    subprocess.run([str(CLI),'pcb','export','svg','--mode-single','--exclude-drawing-sheet','--layers','B.Cu,Edge.Cuts','--mirror','--page-size-mode','2','-o',str(OUT/f'back-tracks-{label}.svg'),str(plot)],check=True,capture_output=True)
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板 · 背面走线整理</title><style>
*{box-sizing:border-box}body{margin:0;background:#f2f5f8;color:#24384d;font:16px/1.7 'Microsoft YaHei',sans-serif}main{max-width:1300px;margin:auto;padding:30px}.note{background:#fff1d0;padding:14px 18px;border-left:4px solid #b78d25}.cards,.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.cards{grid-template-columns:repeat(3,1fr);margin:24px 0}.cards div,section{background:#fff;border:1px solid #dce4ec;padding:18px;border-radius:8px}.big{font-size:28px;color:#176350;font-weight:bold}h1{margin:0;font-size:30px}h2{font-size:21px;margin:0 0 12px}img{width:100%;height:auto}.badge{color:#176350;font-weight:bold}a{color:#1765a1}table{width:100%;border-collapse:collapse;background:#fff;margin:20px 0}th,td{padding:10px 15px;border-bottom:1px solid #dce4ec;text-align:left}th{background:#263b50;color:#fff}button{padding:9px 18px;background:#fff;border:1px solid #8aa1b6;border-radius:5px;font:inherit;cursor:pointer;margin:8px 8px 15px 0}button.active{background:#263b50;color:#fff}.hint{color:#546a7d}.hide{display:none}@media(max-width:800px){.grid,.cards{grid-template-columns:1fr}main{padding:18px}}</style>
<main><h1>语音对讲主板 · 背面走线整理</h1><p>100×75mm · 两层板 · 保留器件位置与原理图连接</p><p class="note">本次完成连续折线简化、冗余长地线清理与两处局部接地补接。整板布局、准确选型、USB/射频及新板实测仍未完成，未生产放行。</p>
<div class="cards"><div>背面线段数量<div class="big">BEFORE_SEG → AFTER_SEG</div>减少 SEG_DROP%</div><div>背面连续转角<div class="big">BEFORE_TURN → AFTER_TURN</div>按非共线的二路连接点统计</div><div>原生连接检查<div class="big">全部通过</div>DRC错误/警告/未连接/连接差异均为0</div></div>
<p>正常45°转角保留。本次主要移除与铺铜重复的长地线；局部电源回流线、地过孔、隔离电池负极保留。两个失去接地的焊盘补接背面地铜，填充后的整个GND网络为一个连通分量。</p>
<button class="active" onclick="view('tracks',this)">走线对比</button><button onclick="view('copper',this)">含铺铜对比</button>
<div class="grid" id="tracks"><section><h2>整理前 · 背面走线</h2><img src="back-tracks-before.svg"></section><section><h2>整理后 · 背面走线</h2><img src="back-tracks-after.svg"></section></div>
<div class="grid hide" id="copper"><section><h2>整理前 · 背面铜层</h2><img src="back-before.svg"></section><section><h2>整理后 · 背面铜层</h2><img src="back.svg"></section></div>
<p class="hint">两张图均镜像为从背面观看。走线对比暂隐藏铺铜以显示路线，实际PCB仍保留铺铜。颜色是KiCad铜层显示颜色，不是阻焊颜色或金属表面处理。</p>
<table><tr><th>1000块量产核算</th><th>每块</th><th>依据</th></tr><tr><td>此前全部接口规划预算</td><td>54.64元</td><td>保留用户4G 10元、ESP32 12元目标</td></tr><tr><td>核查参考价＋国产SIM候选</td><td>COST_FULL元</td><td>候选封装待核；其余未核价部分仍含预算</td></tr><tr><td>上述候选＋雷达/TTL不默认焊排针</td><td>COST_LOW元</td><td>焊孔保留；加工节省按历史焊点费估算</td></tr></table>
<p>走线变整齐本身不降低同尺寸PCB单价。降本来自选料与装配；当前未获得完整嘉立创审单报价，不能保证50元内。功放已用4.52元参考价重算。<a href="../cost/量产降本核算.md">查看逐项成本与边界</a></p>
<section><h2>当前正面</h2><img style="max-width:750px" src="front.svg"></section><p><a href="back-cleanup-validation.json">本版检查记录</a> · <a href="../voice_mainboard_v7.kicad_pcb">PCB工作文件</a> · <a href="../README.md">工程状态</a></p></main>
<script>function view(id,button){for(const key of ['tracks','copper'])document.getElementById(key).classList.toggle('hide',key!==id);for(const b of document.querySelectorAll('button'))b.classList.toggle('active',b===button)}</script></html>'''
oldB=before_stats['B.Cu'];newB=after_stats['B.Cu']
for key,value in {'BEFORE_SEG':oldB['segments'],'AFTER_SEG':newB['segments'],'SEG_DROP':f'{(1-newB["segments"]/oldB["segments"])*100:.1f}','BEFORE_TURN':oldB['degree_two_turns'],'AFTER_TURN':newB['degree_two_turns']}.items():html=html.replace(key,str(value))
# Cost builder is executed after promotion, so it binds the current PCB hash.
subprocess.run([str(REPO/'build/cad-tools/kicad/bin/python.exe'),str(ROOT/'cost/build_cost_options.py')],check=True)
cost=json.loads((ROOT/'cost/量产降本核算.json').read_text(encoding='utf-8'))['summary']
html=html.replace('COST_FULL',f'{cost["full_headers_conditional_board"]:.2f}').replace('COST_LOW',f'{cost["production_conditional_board"]:.2f}')
(OUT/'review.html').write_text(html,encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
