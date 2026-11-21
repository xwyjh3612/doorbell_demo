"""Readable SVG overview + self-contained interactive review of actual RC runs."""
from pathlib import Path
from html import escape
import json, pcbnew as pcb
ROOT=Path(__file__).resolve().parent
d=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
sim=json.loads((ROOT/'exports/power-simulation.json').read_text(encoding='utf-8'))
b=pcb.LoadBoard(str(ROOT/'voice_mainboard_v2.kicad_pcb'))
S,X,Y=8.8,55,175
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1560" height="1150" viewBox="0 0 1560 1150">',
 '<style>text{font-family:"Microsoft YaHei",Arial,sans-serif}</style>',
 '<rect width="1560" height="1150" fill="#eef3f8"/>']
def text(s,x,y,size=18,color='#1b3149',anchor='start',weight='normal'):
    svg.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}" font-weight="{weight}">{escape(s)}</text>')
def rect(x,y,w,h,fill,stroke='none',radius=0):svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" rx="{radius}"/>')
text('语音对讲主板 V2',55,57,34,weight='bold')
text('ML307R-DL 直接贴板 · UPS预留 · USB Host选装 · 电池采样',55,94,20,'#536b82')
rect(1055,35,450,59,'#fff0d6',radius=12)
text('未布线工程草图 · 不可下单',1280,73,24,'#915100','middle','bold')
rect(X,Y,100*S,75*S,'#124e47','#072f2a',7)
for fp in b.GetFootprints():
    ref=fp.GetReference()
    if ref.startswith('H'):
        p=fp.GetPosition();svg.append(f'<circle cx="{X+pcb.ToMM(p.x)*S}" cy="{Y+pcb.ToMM(p.y)*S}" r="14" fill="#eef3f8"/>');continue
    bounds=fp.GetBoundingBox(False,False)
    a,bb,w,h=[pcb.ToMM(z) for z in [bounds.GetX(),bounds.GetY(),bounds.GetWidth(),bounds.GetHeight()]]
    rect(X+a*S,Y+bb*S,w*S,h*S,'none','#4f9282')
    for p in fp.Pads():
        pos,size=p.GetPosition(),p.GetSize();x,y=pcb.ToMM(pos.x),pcb.ToMM(pos.y);pw,ph=pcb.ToMM(size.x),pcb.ToMM(size.y)
        svg.append(f'<rect x="{X+x*S-pw*S/2}" y="{Y+y*S-ph*S/2}" width="{pw*S}" height="{ph*S}" rx="1" fill="#e9c56c" transform="rotate({-p.GetOrientationDegrees()} {X+x*S} {Y+y*S})"/>')
        if p.GetAttribute()!=pcb.PAD_ATTRIB_SMD:
            r=pcb.ToMM(p.GetDrillSize().x)*S/2
            if r:svg.append(f'<circle cx="{X+x*S}" cy="{Y+y*S}" r="{r}" fill="#124e47"/>')
    text(ref,X+a*S,Y+bb*S-2,10,'#ddf3eb',weight='bold')
ux,uy,uw,uh=d['ups_reserved_region_mm']
rect(X+ux*S,Y+uy*S,uw*S,uh*S,'#244f65','#7bb3ce',6)
text('UPS预留',X+(ux+uw/2)*S,Y+(uy+11)*S,23,'#e2eff9','middle','bold')
text('芯片待提供',X+(ux+uw/2)*S,Y+(uy+17)*S,15,'#c5ddea','middle')
text('23 × 28 mm',X+(ux+uw/2)*S,Y+(uy+23)*S,14,'#c5ddea','middle')
# Reserve overlay is conceptual; the draft input header is adjacent to/inside border.
text('100 mm 暂定板框',495,150,17,'#59758d','middle')
text('75 mm',970,509,17,'#59758d','middle')
rect(1030,137,475,698,'white',radius=12)
text('本轮已确定',1055,179,25,weight='bold')
notes=[('ML307R-DL裸模组','109焊盘；VBAT约3.8V；UART 1.8V'),
 ('J1 圆口电源','5.5外径 / 2.5内径；5V中心正极'),
 ('J18 四针TTL刷机','GND / TX43 / RX44 / 5V；3.3V串口'),
 ('SW1 / SW2','BOOT及RESET；四针口手动进下载'),
 ('UPS接口与预留区','芯片后续提供；充放电电路待补'),
 ('电池ADC','GPIO2建议；GPIO9开关；比例2.5'),
 ('USB Host / 维修选装','GPIO20 D+ / 19 D−；两组0Ω互斥'),
 ('音频 / 雷达 / 生产确认','雷达TX→6；封装、外壳与布线待定')]
for i,(a,bb) in enumerate(notes):
    y=225+i*73;text(a,1055,y,19,weight='bold');text(bb,1055,y+28,16,'#627b91')
rect(55,873,1450,217,'white',radius=12)
text('电源与电量：已运行RC仿真，完整UPS尚未定型',80,917,24,weight='bold')
text('电池4.2V → ADC约1.68V；开启采样后建议等待60ms；电量使用电芯曲线分段估算。',80,955,20)
text('理想3.8V源 + 0.3→2A负载：路径50 / 150 / 300mΩ时最低约3.70 / 3.50 / 3.20V。',80,991,19)
text('以上不是UPS、降压反馈或射频的完整仿真；电源切换、温升与实际通话还需实测。',80,1028,19,'#986311')
text('100×75mm与外壳内尺寸、孔位未匹配；图中为真实候选焊盘，不含开发板/音频模块的实际安装占地。',80,1061,17,'#627b91')
svg.append('</svg>')
(ROOT/'exports/overview.svg').write_text('\n'.join(svg),encoding='utf-8')
data=json.dumps(sim,ensure_ascii=False).replace('</','<\/')
html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>语音对讲主板 V2 工程审查</title><style>
body{margin:0;background:#eef3f8;color:#203650;font-family:"Microsoft YaHei",Arial,sans-serif}main{max-width:1500px;margin:auto;padding:24px}
h1{font-size:28px;margin:0 0 12px}p{line-height:1.7}.banner{padding:14px 18px;background:#fff0d6;border-radius:12px;color:#865000}
.panel{background:white;border-radius:16px;padding:24px;margin:20px 0}img{width:100%;height:auto}button{border:1px solid #c1d3e2;border-radius:8px;padding:9px 14px;background:white;color:#203650;cursor:pointer;margin-right:10px}button.active{background:#12655d;color:white}
canvas{display:block;width:100%;height:320px}.row{display:flex;gap:20px;flex-wrap:wrap}.row>section{flex:1;min-width:360px}a{color:#12655d}
table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #dee7ef;text-align:left}.small{color:#627b91;font-size:14px}
</style><main><h1>语音对讲主板 V2</h1><p class="banner">未布线工程草图；UPS芯片和部分采购封装待确定，不能下单生产。板图生成不接触正在测试的设备。</p>
<div class="panel"><img src="overview.svg" alt="ML307贴片、UPS预留及TTL口的实际焊盘摆放草图"></div>
<div class="panel"><h2>预留USB，保留当前AT</h2><p>模组59/60脚连接D+/D−，ESP32-S3预留GPIO20/19。UART17/18及DTR4保留。Host连接完成后可做AT、RNDIS、ECM编译选择；正式固件统一选择及热切换尚未实现。</p>
<table><tr><th>贴装用途</th><th>贴装0Ω</th><th>不贴</th></tr><tr><td>默认：电脑维修模组</td><td>R26 / R27 / R30</td><td>R28 / R29 / R31</td></tr><tr><td>产品：ESP32 USB Host</td><td>R28 / R29 / R31</td><td>R26 / R27 / R30</td></tr></table>
<p>两组互斥；USB VBUS为检测端，不能代替3.8V主电源。差分90Ω、ESD及最终连接器待设计，尚未完成实机USB枚举/通话验证。</p></div>
<div class="panel"><h2>扩展仿真审查</h2><p>已检查采样开关、按钮、模组控制、电源负载及接口。外部检测阈值已修正并通过27组通用模型情景，降压闭环、UPS和实物检测尚未验证，整机未通过验收。</p><p><a href="function-simulation/index.html">打开完整覆盖表、波形及失败项</a> · <a href="../首板设计与验收.md">首板设计与验收要求</a></p></div>
<div class="panel"><h2>实际 ngspice RC 仿真</h2><div class="row"><section><h3>电池分压开启</h3><canvas id="adc" width="1200" height="640"></canvas><p>150kΩ / 100kΩ + 100nF；输入4.2V，稳态1.68V。建议等待60ms后取样。</p></section>
<section><h3>模组供电阻抗</h3><div id="choices"></div><canvas id="modem" width="1200" height="640"></canvas><p id="voltage"></p></section></div><p class="small">理想电源与集总RC模型，未包含UPS切换、降压芯片反馈、线缆电感或射频。这里通过不能替代硬件负载测试。</p></div>
<div class="panel"><h2>4针刷机口 J18</h2><table><tr><th>针序</th><th>板端</th><th>USB-TTL端</th></tr><tr><td>1</td><td>GND</td><td>GND</td></tr><tr><td>2</td><td>TX43</td><td>RX</td></tr><tr><td>3</td><td>RX44</td><td>TX</td></tr><tr><td>4</td><td>5V可选供电</td><td>5V；信号电平3.3V</td></tr></table><p>主电源供电时TTL的5V可不接。JP3选择系统/TTL给ESP32供电。按住BOOT，按下并松开RESET，再松开BOOT即可手动进入下载。</p>
<p><a href="schematic/voice_mainboard_v2.svg">打开完整原理图</a> · <a href="validation.json">网表与设计检查</a> · <a href="power-simulation.json">仿真原始数据</a></p></div></main>
<script>const sim=__DATA__;
function plot(id,t,v,xmax,ymin,ymax,threshold){const c=document.getElementById(id),g=c.getContext('2d'),w=c.width,h=c.height;g.clearRect(0,0,w,h);const l=100,r=w-35,top=45,bot=h-75;const x=z=>l+z/xmax*(r-l),y=z=>bot-(z-ymin)/(ymax-ymin)*(bot-top);g.font='25px Arial';g.lineWidth=2;
 for(let i=0;i<=5;i++){let val=ymin+(ymax-ymin)*i/5;g.strokeStyle='#e1e8ef';g.beginPath();g.moveTo(l,y(val));g.lineTo(r,y(val));g.stroke();g.fillStyle='#627b91';g.fillText(val.toFixed(2)+'V',8,y(val)+8)}
 for(let i=0;i<=4;i++){let val=xmax*i/4;g.fillText(val.toFixed(0)+'ms',x(val)-25,h-25)}
 if(threshold){g.strokeStyle='#b85639';g.setLineDash([12,8]);g.beginPath();g.moveTo(l,y(threshold));g.lineTo(r,y(threshold));g.stroke();g.setLineDash([]);g.fillStyle='#b85639';g.fillText('3.4V minimum',r-220,y(threshold)-12)}
 g.strokeStyle='#12655d';g.lineWidth=4;g.beginPath();t.forEach((a,i)=>{let xx=x(a*1000),yy=y(v[i]);i?g.lineTo(xx,yy):g.moveTo(xx,yy)});g.stroke()}
plot('adc',sim.battery_adc.trace.time,sim.battery_adc.trace['v(adc)'],60,0,1.8);
const cases=sim.modem_transient.cases;function choose(i){document.querySelectorAll('button').forEach((b,j)=>b.classList.toggle('active',i===j));let a=cases[i];plot('modem',a.trace.time,a.trace['v(modem)'],4,3.0,3.9,3.4);document.getElementById('voltage').textContent='供电路径 '+Math.round(a.path_resistance_ohm*1000)+'mΩ；最低电压 '+a.minimum_v.toFixed(3)+'V。'}
cases.forEach((a,i)=>{let b=document.createElement('button');b.textContent=Math.round(a.path_resistance_ohm*1000)+'mΩ';b.onclick=()=>choose(i);document.getElementById('choices').append(b)});choose(1);
</script></html>'''.replace('__DATA__',data)
(ROOT/'exports/review.html').write_text(html,encoding='utf-8')
print('Generated actual-pad SVG and self-contained RC review HTML')
