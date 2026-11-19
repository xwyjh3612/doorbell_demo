"""Render a labelled vector placement overview and true-size hole template.

Uses the actual KiCad footprint/pad positions. These are engineering review
drawings, not manufacturing plots or claims about physical module dimensions.
"""
from pathlib import Path
from html import escape
import json, pcbnew as pcb
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
board=pcb.LoadBoard(str(ROOT/'voice_carrier_v1.kicad_pcb'))
S,X,Y=10,60,155
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1460" height="1080" viewBox="0 0 1460 1080">',
 '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif}.mono{font-family:Consolas,monospace}</style>',
 '<rect width="1460" height="1080" fill="#f3f6fa"/>']
def text(label,x,y,size=19,color='#22364c',weight='normal',anchor='start'):
    svg.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(label)}</text>')
def rect(x,y,w,h,fill,stroke='none',radius=0):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')
text('语音对讲 V1 · 连接底板',60,60,32,weight='bold')
text('保留已调通模块，通过线束连接；生命体征模块后装',60,99,19,'#546980')
rect(1040,39,355,55,'#fff1df',radius=14)
text('摆放草图 · 未布线 · 不可下单',1217,74,20,'#9b4a04','bold','middle')
rect(X,Y,900,650,'#124d42','#082d27',8)
for x,y in [(4,4),(86,4),(4,61),(86,61)]:
    svg.append(f'<circle cx="{X+x*S}" cy="{Y+y*S}" r="16" fill="#f3f6fa"/>')
for fp in board.GetFootprints():
    ref=fp.GetReference()
    if ref.startswith('H'):continue
    bounds=fp.GetBoundingBox(False,False)
    a,b,w,h=[pcb.ToMM(z) for z in [bounds.GetX(),bounds.GetY(),bounds.GetWidth(),bounds.GetHeight()]]
    rect(X+a*S,Y+b*S,w*S,h*S,'none','#72ac89',1)
    for pad in fp.Pads():
        pos,size=pad.GetPosition(),pad.GetSize()
        x,y=pcb.ToMM(pos.x),pcb.ToMM(pos.y)
        w,h=pcb.ToMM(size.x),pcb.ToMM(size.y)
        # Rectangular pad outlines rotated with the real footprint.
        angle=-pad.GetOrientationDegrees()
        svg.append(f'<rect x="{X+x*S-w*S/2}" y="{Y+y*S-h*S/2}" width="{w*S}" height="{h*S}" rx="1" fill="#e7c86e" transform="rotate({angle} {X+x*S} {Y+y*S})"/>')
        if pad.GetAttribute()!=pcb.PAD_ATTRIB_SMD:
            drill=pcb.ToMM(pad.GetDrillSize().x)
            svg.append(f'<circle cx="{X+x*S}" cy="{Y+y*S}" r="{drill*S/2}" fill="#124d42"/>')
    text(ref,X+a*S,Y+b*S-3,11,'#e4f5d7',weight='bold')
svg.append(f'<path d="M{X} 132 v-10 h900 v10 M{X+925} {Y} h10 v650 h-10" fill="none" stroke="#657d94"/>')
text('90 mm（暂定板框）',510,118,16,anchor='middle')
text('65 mm',1011,494,16,anchor='middle')
rect(1045,155,355,650,'#fff',radius=12)
text('接口与结构',1068,190,23,weight='bold')
notes=[
 ('J1  外部稳压输入','约5.2V；适配器型号待确定'),
 ('J2  单节受保护电池','容量/尺寸/放电规格待固定'),
 ('J3 / J6  自研4G板','电源和UART分别连接'),
 ('J5  ESP32线束接口','2×12排针，不能直接套开发板'),
 ('J7 / J8  麦克风与功放','麦克风3.3V；功放系统5V'),
 ('J9 + JP2  可选雷达','TX → GPIO6；RX ← 预留GPIO8'),
 ('J10 + JP1  呼叫按钮','常开自复位；GPIO0/9可选择'),
 ('四个M3孔','通用孔位，未匹配外壳螺柱'),
]
for i,(a,b) in enumerate(notes):
    y=232+i*69
    text(a,1068,y,18,weight='bold');text(b,1068,y+27,15,'#65778d')
rect(60,844,1340,188,'#fff',radius=12)
text('机械尺寸核对后再完成PCB',84,886,23,weight='bold')
text('已知公开规格：R60ABD1 35×31×7.5mm；芯片与标准接插件有封装图。',84,923,19)
text('待测实物：ESP32板、4G板、喇叭、麦克风/功放板，以及外壳内尺寸和螺柱位置。',84,956,19)
text('当前检查：原理图ERC 0违规；摆放几何 0违规；132处未布线；电源性能及整机安装未验证。',84,991,17,'#8f4a10')
svg.append('</svg>')
(ROOT/'exports/overview.svg').write_text('\n'.join(svg),encoding='utf-8')

template=['<svg xmlns="http://www.w3.org/2000/svg" width="90mm" height="65mm" viewBox="0 0 90 65">',
 '<rect x="0.2" y="0.2" width="89.6" height="64.6" fill="white" stroke="black" stroke-width="0.2"/>']
for x,y in [(4,4),(86,4),(4,61),(86,61)]:
    template.append(f'<circle cx="{x}" cy="{y}" r="1.6" fill="none" stroke="black" stroke-width="0.15"/><path d="M{x-2} {y}h4 M{x} {y-2}v4" stroke="black" stroke-width="0.1"/>')
template += ['<text x="45" y="23" font-family="Arial" font-size="3" text-anchor="middle">90 x 65 mm - PLACEMENT DRAFT</text>',
 '<text x="45" y="30" font-family="Arial" font-size="2.5" text-anchor="middle">Generic M3 holes / enclosure fit UNVERIFIED</text>',
 '<path d="M35 43 v-2 M35 42 h20 M55 43 v-2" stroke="black" stroke-width="0.2"/>',
 '<text x="45" y="48" font-family="Arial" font-size="2.5" text-anchor="middle">20 mm scale - print at actual size</text>','</svg>']
(ROOT/'exports/hole-template-1to1.svg').write_text('\n'.join(template),encoding='utf-8')
print('Created vector overview and 1:1 hole template')
