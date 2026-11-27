"""Promote the checked RGB working revision, retaining hash-bound history."""
import hashlib,json,shutil,subprocess
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
CAND=ROOT/'indicator_revision';FILE=CAND/'voice_mainboard_v7.kicad_pcb'
CLI=REPO/'build/cad-tools/kicad/bin/kicad-cli.exe'
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
dr=json.loads((CAND/'exports/drc.json').read_text(encoding='utf-8'))
er=json.loads((CAND/'exports/erc.json').read_text(encoding='utf-8'))
assert not dr['violations']and not dr['unconnected_items']and not dr['schematic_parity']
assert not any(sheet['violations']for sheet in er['sheets'])
ground=json.loads((CAND/'ground-components.json').read_text(encoding='utf-8'))
assert len(ground)==1
before=p.LoadBoard(str(ROOT/FILE.name));after=p.LoadBoard(str(FILE))
def pads(b):return {(f.GetReference(),d.GetNumber()):(d.GetNetname(),d.GetPosition().x,d.GetPosition().y)for f in b.GetFootprints()for d in f.Pads()}
a,z=pads(before),pads(after)
changed={k for k in a if a[k]!=z[k]}
assert changed=={('U7','31'),('U7','32'),('U7','34')},changed
assert {k[0]for k in z if k not in a}=={'D2','R77','C74'}
frozen={'CELL_NEG','VIN_FUSED','RF_ANT','RF_FEED','M_USB_DP','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19','SERVICE_USB_DP','SERVICE_USB_DM','BUCK_SW','UPS_SW','ESP_SW'}
def copper(b):
    rows=[]
    for t in b.GetTracks():
        if t.GetNetname()not in frozen:continue
        if isinstance(t,p.PCB_VIA):rows.append((t.GetNetname(),'via',t.GetPosition().x,t.GetPosition().y,t.GetWidth(p.F_Cu),t.GetDrill()))
        else:rows.append((t.GetNetname(),'track',t.GetLayer(),t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth()))
    return sorted(rows)
assert copper(before)==copper(after)
assert z['U7','31'][0]=='CHG_DISABLE_IO38'and z['U7','32'][0]=='STATUS_LED_IO39'
assert z['D2','1'][0]=='unconnected-(D2-DO-Pad1)'
assert [z['D2',str(i)][0]for i in [2,3,4]]==['GND','RGB_LED_DIN','ESP_3V3']
d2=next(f for f in after.GetFootprints()if f.GetReference()=='D2')
assert d2.GetOrientationDegrees()==180
x,y=p.ToMM(d2.GetPosition().x),p.ToMM(d2.GetPosition().y)
expected={1:(x+.915,y+.55),2:(x+.915,y-.55),3:(x-.915,y-.55),4:(x-.915,y+.55)}
for n,xy in expected.items():assert all(abs(v-w)<.00001 for v,w in zip((p.ToMM(z['D2',str(n)][1]),p.ToMM(z['D2',str(n)][2])),xy))
official={4:4,5:5,6:6,7:7,8:15,9:16,10:17,11:18,12:8,13:19,14:20,15:3,16:46,17:9,18:10,19:11,20:12,21:13,22:14,23:21,24:47,25:48,26:45,27:0,28:35,29:36,30:37,31:38,32:39,33:40,34:41,35:42,36:44,37:43,38:2,39:1}
expected_gpio_nets={'ESP_DTR4':4,'RADAR_RX6':6,'I2S_SPK_DATA7':7,'I2S_SPK_BCLK15':15,'I2S_SPK_WS16':16,'ESP_TX17':17,'ESP_RX18':18,'RADAR_TX8':8,'ESP_USB_DM19':19,'ESP_USB_DP20':20,'BAT_ADC_EN9':9,'EXT_PRESENT_N_IO10':10,'PWRKEY_CTL':11,'I2S_MIC_DATA12':12,'I2S_MIC_WS13':13,'I2S_MIC_BCLK14':14,'RESET_CTL':21,'SUPPLY_BAT_N47':47,'CHG_ACTIVE_N':48,'CALL_BOOT0':0,'CHG_DISABLE_IO38':38,'STATUS_LED_IO39':39,'DEBUG_ESP_RX44':44,'DEBUG_ESP_TX43':43,'BAT_ADC2':2,'CHG_FULL_N':1}
for (ref,n),(net,_,_)in z.items():
    if ref=='U7'and net in expected_gpio_nets:assert official[int(n)]==expected_gpio_nets[net],(n,net)
data=json.loads((CAND/'design.json').read_text(encoding='utf-8'))
fps={f.GetReference():f for f in after.GetFootprints()}
for q in data['parts']:
    if q['ref']in fps:
        f=fps[q['ref']];q.update(x=p.ToMM(f.GetPosition().x),y=p.ToMM(f.GetPosition().y),angle=f.GetOrientationDegrees())
data.update(revision='V7-RGB-WORKING-20261124',status='RGB AND GPIO38 PAD CORRECTION CHECKED; NOT MANUFACTURING RELEASED')
data['indicators']['rgb']['firmware_implemented']=True
(CAND/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
history=ROOT/'history/20261124-before-rgb';history.mkdir(exist_ok=True)
names=[FILE.name,'voice_mainboard_v7.kicad_sch','voice_mainboard_v7.kicad_pro','voice_mainboard_v7.kicad_dru','VoiceV2.kicad_sym','design.json','README.md']
assert not(history/FILE.name).exists(),'Promotion already performed; do not overwrite baseline'
for name in names:shutil.copy2(ROOT/name,history/name)
shutil.copytree(ROOT/'exports',history/'exports',dirs_exist_ok=True)
for name in names:
    if name!='README.md':shutil.copy2(CAND/name,ROOT/name)
out=ROOT/'exports'
for name in ['drc.json','erc.json','indicator-changes.json','rgb-ground-changes.json','supply-corridor-changes.json']:
    if(CAND/'exports'/name).exists():shutil.copy2(CAND/'exports'/name,out/name)
shutil.copy2(CAND/'ground-components.json',out/'ground-components.json')
report={'date':'2026-11-24','PCB_sha256':sha(ROOT/FILE.name),'schematic_sha256':sha(ROOT/'voice_mainboard_v7.kicad_sch'),'base_PCB_sha256':sha(history/FILE.name),'DRC_errors':0,'DRC_warnings':0,'unconnected':0,'schematic_parity':0,'ERC_errors':0,'ERC_warnings':0,'ground_geometric_components':1,'added_parts':['D2','R77','C74'],'RGB_model':'WS2812B-2020-V6','LCSC':'C52917434','GPIO':39,'module_pin':32,'supply':'ESP_3V3','3V3_supply_corner_qualified':False,'physical_LED_color_test_completed':False,'existing_footprint_positions_unchanged':True,'existing_GPIO_net_changes':{'U7.31':'GPIO38 charger control','U7.32':'GPIO39 RGB data','U7.34':'GPIO41 unused'},'official_active_GPIO_mapping_checked':expected_gpio_nets,'official_source':'build/v4-reference/esp32-s3-wroom-1.txt pages11/12; https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf','RGB_pin_map_checked':{'1':'DO bottom-right NC','2':'GND top-right','3':'DI top-left','4':'VDD bottom-left'},'RGB_datasheet':'../sources/rgb-20261124/WS2812B-2020-V6.pdf','USB_RF_switch_input_and_cell_copper_unchanged':True,'full_board_simulated':False,'manufacturing_ready':False,'firmware_checks':{v:json.loads((REPO/f'outputs/firmware/{v}.json').read_text(encoding='utf-8-sig'))for v in ['mainboard-v7','voice-radar60']},'host_state_and_pulse_test_passed':True,'price':{'source':'https://item.szlcsc.com/55827425.html','D2_1':.5585,'D2_100':.3469,'D2_1000':.3198,'passive_material_allowance':.04,'material_budget_per_board':.4,'assembly_quote_obtained':False},'remaining':['New-board power/NTC/cell qualification','3V3 low-supply corner and RGB optical test','USB/RF and full-board qualification','Exact procurement and assembly quote; no hardware flash in this change']}
(out/'rgb-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,layers,mirror in [('front.svg','F.Cu,F.SilkS,Edge.Cuts',False),('back.svg','B.Cu,B.SilkS,Edge.Cuts',True)]:
    args=[str(CLI),'pcb','export','svg','--mode-single','--exclude-drawing-sheet','--layers',layers,'--page-size-mode','2','-o',str(out/name)]
    if mirror:args.append('--mirror')
    subprocess.run(args+[str(ROOT/FILE.name)],check=True,capture_output=True)
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板 · RGB状态灯</title><style>*{box-sizing:border-box}body{margin:0;background:#f2f5f8;color:#24384d;font:16px/1.7 'Microsoft YaHei',sans-serif}main{max-width:1250px;margin:auto;padding:28px}h1{margin:0}h2{font-size:21px;margin:0 0 12px}.note{background:#fff1d0;padding:14px;border-left:4px solid #b78d25}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}section{background:white;border:1px solid #dce4ec;padding:18px;border-radius:8px}img{width:100%;height:auto}table{width:100%;border-collapse:collapse;background:white;margin:20px 0}td,th{padding:10px;border-bottom:1px solid #dce4ec;text-align:left}th{background:#263b50;color:white}a{color:#1765a1}.dot{display:inline-block;width:13px;height:13px;border-radius:50%;margin-right:8px}p{margin:12px 0}@media(max-width:800px){.grid{grid-template-columns:1fr}main{padding:18px}}</style><main><h1>语音对讲主板 · 单颗RGB状态灯</h1><p>V7工作版 · 100×75mm · 两层板 · D2位于正面上沿（72mm，3mm）</p><p class="note">RGB及GPIO38引脚纠正已通过CAD连接检查；当前工作版仍未生产放行。整板实测、NTC/电池规格、电源峰值、USB/RF及RGB低压供电验证待完成。</p><div class="grid"><section><h2>一个灯，显示四种状态</h2><p><span class="dot" style="background:#df5353"></span>红色慢闪：未联网 / MQTT未就绪</p><p><span class="dot" style="background:#29a975"></span>绿色双闪：在线待机</p><p><span class="dot" style="background:#3e80df"></span>蓝色快闪：呼叫 / 呼入 / 正在连接</p><p><span class="dot" style="background:#3e80df"></span>蓝色长亮、短暂熄灭：通话中</p><p>GPIO39 → 330Ω → RGB DI；100nF去耦。读取本地状态，RMT硬件产生波形；低优先级任务不发送AT命令。灯不是独立供电指示或硬件看门狗。</p></section><section><h2>本次检查</h2><p>原生DRC错误、警告、未连接及连接差异均为0；ERC错误、警告均为0。填充GND为一个连通分量。</p><p>按官方ESP模组表核对全部已用GPIO：GPIO39对应模组32脚；充电暂停GPIO38纠正到模组31脚，模组34脚实际为GPIO41。</p><p>V7无雷达固件与现开发板60GHz雷达固件已编译并验证功能包含/排除；灯色、闪烁、长运行时间的主机逻辑测试通过。没有刷机或实测新主板。</p></section></div><table><tr><th>WS2812B-2020-V6（C52917434）</th><th>公开参考单价</th></tr><tr><td>少量</td><td>0.5585元</td></tr><tr><td>100颗</td><td>0.3469元</td></tr><tr><td>1000颗</td><td>0.3198元</td></tr><tr><td>含电阻、电容的量产材料预算</td><td>约0.4元/台；新增贴装/换料费用另行审单</td></tr></table><p><a href="https://item.szlcsc.com/55827425.html">公开价格来源</a>。厂家标明支持3.3V；新板仍须测量供电容差、启动与欠压时的颜色/亮度。此前整板51.46/52.33元核算属于加灯前的条件预算。</p><div class="grid"><section><h2>当前正面 · 上沿RGB</h2><img src="front.svg"></section><section><h2>当前背面 · 镜像观看</h2><img src="back.svg"></section></div><p><a href="../voice_mainboard_v7.kicad_pcb">PCB工作文件</a> · <a href="../voice_mainboard_v7.kicad_sch">原理图</a> · <a href="rgb-validation.json">本版校验记录</a> · <a href="../README.md">工程状态</a> · <a href="../history/20261124-before-rgb/exports/review.html">加灯前背面走线对比</a></p></main></html>'''
(out/'review.html').write_text(html,encoding='utf-8')
print(json.dumps({k:v for k,v in report.items()if k not in ['firmware_checks','official_active_GPIO_mapping_checked']},ensure_ascii=False,indent=2))
