"""Build a 5-unit RFQ list and readable circuit sheets from the actual pin map.

Run with Python + reportlab. Outputs are for engineering quotation/review;
unrouted PCB and unsettled procurement items are explicitly retained.
"""
from pathlib import Path
import json, csv, math, re
from collections import OrderedDict
from html import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[1]
OUT=PROJECT/'outputs/first5-supplier'
OUT.mkdir(parents=True,exist_ok=True)
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
parts={p['ref']:p for p in data['parts'] if p['kind']!='mechanical'}
physical={r:p for r,p in parts.items() if not r.startswith('TP')}
core={
 'U1':('TP4056 / TPOWER','ESOP8 / SOP8-PP','C382139','固定品牌；同名不同厂不得直接替换；散热焊盘待最终复核'),
 'U2':('TPS61230ARNSR / TI','RNS0007A VQFN-HR-7','C376005','7脚非对称封装；不能用普通QFN替代'),
 'U3':('TPS2117DRLR / TI','DRL0008A SOT-5X3-8','C22399676','8脚0.5mm间距；型号后缀必须一致'),
 'U4':('TLV803EA30DBZR / TI','SOT-23-3 / DBZ','C5218924','开漏、下降阈值3.08V、释放延时200ms；不得换推挽版'),
 'U5':('LM393DR / TI','SOIC-8','','使用无B后缀的LM393DR；不得静默换型号'),
 'U6':('TL431BIDBZR / TI','SOT-23-3 / DBZ','','TI引脚1=K、2=REF、3=A；核对厂家脚序'),
 'D1':('BAT54C,215 / Nexperia','SOT-23-3','','双二极管共阴极；不是BAT54A/单二极管'),
 'L1':('SWPA6045S1R0NT / Sunlord','SMD 6x6mm / 6045','C96955','1uH±30%；额定5.14A、Isat9.85A、DCR11mΩ参考规格')
}
# C numbers only published in already-verified source records are retained below.
# Unknown catalog numbers are left blank; MPN/brand is the purchase constraint.

rows=[]
for ref in core:
    model,package,code,note=core[ref]
    rows.append(dict(category='SMT',refs=[ref],model=model,package=package,unit=1,spare=2,
      spec=note,status='料号确定；设计/封装待复核',code=code,source=parts[ref]['source']))

groups=OrderedDict()
for ref,p in physical.items():
    if ref.startswith('R'):
        val=p['value'];accuracy='0.1%' if '0.1%' in val else '1%'
        numeric=val.split()[0]
        key=('SMT',f'{numeric} {accuracy}','0603 / 公制1608')
        groups.setdefault(key,[]).append(ref)
    elif ref.startswith('C') and ref!='C9':
        value=p['value'].split()[0]
        package='0805 / 公制2012' if '0805' in p['footprint'] else '0603 / 公制1608'
        key=('SMT',f'{value}F ≥10V X5R/X7R ±20%',package)
        groups.setdefault(key,[]).append(ref)
for (cat,model,package),refs in groups.items():
    spec='无固定厂家料号；商家提供实际品牌和型号后确认'
    if refs[0].startswith('R'):spec='≥0.1W；按表中精度；温漂和额定电压按实际系列核对'
    elif any(r in ['C3','C4','C5'] for r in refs):spec='C4/C5在约5.15V直流偏压下的合计有效容量须满足升压要求；提供偏压曲线'
    rows.append(dict(category=cat,refs=refs,model=model,package=package,unit=len(refs),spare=10,
      spec=spec,status='规格明确；实际采购料号待确认',code='',source='design.json / 原厂电容选择要求'))
rows.append(dict(category='THT',refs=['C9'],model='470uF ≥10V 低ESR电解电容',package='径向；直径8mm；脚距3.5mm占位',unit=1,spare=2,
 spec='正极SYS5V；实际料号、高度、ESR/纹波及寿命待确认',status='候选；确认后再采购',code='',source=''))
connector_groups=[
 (['J1','J2','J3'],'2P 5.08mm 接线端子','PCB插件 / 横向','Phoenix MKDS-1,5-2-5.08参考外形；普通同间距端子不能默认匹配；J1/J2按≥5A选型'),
 (['J4','J10','JP2'],'1x2 2.54mm 直排针','PCB插件','镀层、针长、额定电流和塑胶外形需确认'),
 (['J5'],'2x12 2.54mm 直排针','PCB插件','这是自定义线束接口，不是ESP32开发板直插座；供电脚额定电流需核对'),
 (['J6','J9'],'1x4 2.54mm 直排针','PCB插件','UART/可选雷达；保留雷达连接口'),
 (['J7','J8'],'1x5 2.54mm 直排针','PCB插件','麦克风/功放线束接口；电源脚额定电流需核对'),
 (['JP1'],'1x3 2.54mm 直排针','PCB插件','按钮GPIO0/9选择跳线')
]
for refs,model,package,spec in connector_groups:
    rows.append(dict(category='THT',refs=refs,model=model,package=package,unit=len(refs),spare=2,
      spec=spec,status='接口规格；具体供应型号待确认',code='',source=''))
assert sorted(sum([r['refs'] for r in rows],[]))==sorted(physical)
assert sum(r['unit'] for r in rows if r['category']=='SMT')==42
assert sum(r['unit'] for r in rows if r['category']=='THT')==13
for row in rows:row['required5']=row['unit']*5;row['suggested']=row['required5']+row['spare']

modules=[
 ('ESP32-S3开发板','沿用已验证板型；照片丝印ESP32-S3-N16R8',1,5,'已有可复用的扣减；先核板型/尺寸/供电，不能只按N16R8买不同板'),
 ('自研ML307 4G板','沿用自研板及已验证版本',1,5,'淘宝通用ML307板不作为自动替代；确认5V板级入口和UART电平'),
 ('4G天线和连接线','与当前4G板、目标频段和接头一致',1,5,'计入原基础硬件；保持装盒安装留空要求'),
 ('INMP441麦克风模块','沿用已验证模块版本',1,5,'3.3V；L/R焊盘接法沿用当前样机'),
 ('MAX98357 I2S功放模块','沿用已验证模块型号/增益接法',1,5,'5V；SD/GAIN等脚沿用原接法；不是模拟功放'),
 ('喇叭','型号、尺寸、阻抗和额定功率待实物核对',1,5,'保持当前已验证负载；不能先按未知阻抗换更大喇叭'),
 ('单节锂电池包','暂预算1000mAh；4.2V体系；带保护和10k NTC',1,5,'电芯/保护/线/端子≥5A持续放电目标；需规格、尺寸和NTC B值，未定型'),
 ('外部适配器及电源线','候选约5.2V稳压/3A；最终料号待确认',1,5,'系统5V/2A目标另留充电余量；通用5V±5%不保证雷达电压；勿直接按此购买'),
 ('面板呼叫按钮','12mm孔候选；常开自复位、两脚、不带灯',1,5,'实际尾部深度和面板厚度待核对；GPIO/消抖需固件适配'),
 ('外壳和内部支架','现成ABS盒加工或少量打印；尺寸待布局',1,5,'无需首批开模；当前90x65mm底板尚未匹配外壳'),
 ('连接线束','信号与电源分开；明确线径、长度、端子和极性',1,5,'按装配图制作；大电流线路不用松动细杜邦线承担'),
 ('螺丝/支柱/绝缘固定件','M3孔参考；按外壳固定结构确定',1,5,'一套/台；电池不受螺丝和线束挤压'),
 ('2.54mm跳线帽','按钮选择必需1个/台；雷达电源另1个/台',1,5,'基础5个；扩展可再备5个；不焊到PCB上'),
 ('SIM卡及流量','目标运营商/卡型',1,5,'服务费用单列，不计成贴片物料'),
 ('R60ABD1生命体征雷达（可选）','35x31x7.5mm公开规格；厂家串口模块',0,0,'基础款不采购；可先复用已有1块做扩展测试，不替代成裸雷达芯片')
]
modules=[dict(item=a,spec=b,unit=c,required5=d,note=e) for a,b,c,d,e in modules]
(OUT/'supplier-data.json').write_text(json.dumps({'date':'2026-11-19','quantity':5,'status':'询价与工程复核；未发布生产','rows':rows,'modules':modules,'counts':{'SMT_per_board':42,'THT_per_board':13,'SMT_first5':210,'THT_first5':65}},ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'首批5台贴片及插件询价清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['工艺','位号','型号/数值','封装','每板数量','5板净需求','额外备料建议','建议备货量','采购状态','规格/确认项','商品编号','来源','商家实际料号','商家单价'])
    for r in rows:w.writerow([r['category'],','.join(r['refs']),r['model'],r['package'],r['unit'],r['required5'],r['spare'],r['suggested'],r['status'],r['spec'],r['code'],r['source'],'',''])

# Circuit renderer draws PDF and SVG from the same coordinate scene.
pdfmetrics.registerFont(TTFont('Chinese','C:/Windows/Fonts/simhei.ttf'))
pdf=canvas.Canvas(str(OUT/'首批5台语音对讲电路图.pdf'),pagesize=(1122.52,793.70))
pdf.setTitle('语音对讲首批5台电路图 - 工程询价与复核')
W,H=1600,1100
pin_names={
 'U1':['TEMP','PROG','GND','VCC','BAT','STDBY','CHRG','CE','EP'],
 'U2':['CBST','EN','FB','VIN','SW','GND','VOUT'],
 'U3':['GND','VOUT','VIN1','PR1','MODE','VIN2','VOUT','ST'],
 'U4':['GND','RESET_N','VDD'],
 'U5':['OUT1','IN1_N','IN1_P','GND','IN2_P','IN2_N','OUT2','VCC'],
 'U6':['K','REF','A'], 'D1':['A1','A2','K_COMMON']}
drawn={}
svgs=[]
def record(ref):
    assert ref not in drawn,ref
    drawn[ref]=dict(parts[ref]['pins'])
def txt(s,x,y,size=19,color='#213547',anchor='start'):
    assert 0<=x<=W and 0<=y<=H,(s,x,y)
    pdf.setFont('Chinese',size);pdf.setFillColor(HexColor(color))
    if anchor=='middle':pdf.drawCentredString(x,y,s)
    elif anchor=='end':pdf.drawRightString(x,y,s)
    else:pdf.drawString(x,y,s)
    svgs.append(f'<text x="{x}" y="{y}" font-family="SimHei,Microsoft YaHei,Arial,sans-serif" font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')
def line(points,color='#246a57',width=2):
    pdf.setStrokeColor(HexColor(color));pdf.setLineWidth(width)
    for (x1,y1),(x2,y2) in zip(points,points[1:]):pdf.line(x1,y1,x2,y2)
    svgs.append(f'<polyline points="'+ ' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="{width}"/>')
def rect(x,y,w,h,fill='none',stroke='#bcc9d4',width=1):
    pdf.setStrokeColor(HexColor(stroke));pdf.setLineWidth(width)
    pdf.setFillColor(HexColor(fill if fill!='none' else '#ffffff'));pdf.rect(x,y,w,h,stroke=1,fill=int(fill!='none'))
    svgs.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
def dot(x,y):
    pdf.setFillColor(HexColor('#246a57'));pdf.circle(x,y,3,fill=1,stroke=0)
    svgs.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#246a57"/>')
def label(name,x,y,anchor='start'):
    txt(name,x,y,16,'#246a57',anchor)
def section(s,x,y,w,h):
    rect(x,y,w,h,'#ffffff');txt(s,x+20,y+30,23)
def device(ref,x,y,w=270,split=None):
    p=parts[ref];record(ref);nums=list(p['pins']);n=len(nums)
    if split is None:split=math.ceil(n/2)
    rows=max(split,n-split);h=max(135,60+rows*43)
    rect(x,y,w,h,'#f3f6f9','#526d85',2);txt(ref+'  '+p['value'],x+w/2,y+29,18,anchor='middle')
    for i,num in enumerate(nums):
        side=0 if i<split else 1;row=i if side==0 else i-split;py=y+65+row*43
        name=pin_names.get(ref,[])
        desc=name[int(num)-1] if name else num
        if side==0:
            line([(x-65,py),(x,py)]);txt(num+' '+desc,x+10,py-6,16);label(p['pins'][num] or 'NC',x-72,py-6,'end')
        else:
            line([(x+w,py),(x+w+65,py)]);txt(num+' '+desc,x+w-10,py-6,16,anchor='end');label(p['pins'][num] or 'NC',x+w+72,py-6)
    return h
def passive(ref,x,y,span=260):
    p=parts[ref];record(ref);a,b=p['pins']['1'],p['pins']['2']
    scale=span/260
    txt(ref+'  '+p['value'],x+span/2,y-42,18,anchor='middle')
    line([(x,y),(x+100*scale,y)]);line([(x+160*scale,y),(x+span,y)])
    if ref.startswith('R'):
        rect(x+100*scale,y-10,60*scale,20,'#ffffff','#246a57',2)
    elif ref.startswith('C'):
        line([(x+120*scale,y-19),(x+120*scale,y+19)]);line([(x+140*scale,y-19),(x+140*scale,y+19)])
        line([(x+100*scale,y),(x+120*scale,y)]);line([(x+140*scale,y),(x+160*scale,y)])
        if ref=='C9':txt('+',x+105*scale,y-22,17)
    elif ref.startswith('L'):
        pts=[(x+(100+i*60/64)*scale,y-12*abs(math.sin(i*math.pi/16))) for i in range(65)];line(pts)
    label(a,x,y+30);label(b,x+span,y+30,'end')
def group_passives(refs,x,y,columns=2,dx=385,dy=105,span=260):
    for i,r in enumerate(refs):passive(r,x+(i%columns)*dx,y+(i//columns)*dy,span)
def connector(ref,x,y,w=385):
    p=parts[ref];record(ref);n=len(p['pins']);h=65+n*29
    rect(x,y,w,h,'#f5f8fa');txt(ref+'  '+p['value'],x+17,y+27,19)
    for i,(num,name) in enumerate(p['pins'].items()):
        yy=y+58+i*29
        line([(x+20,yy-5),(x+55,yy-5)]);dot(x+20,yy-5);txt(num,x+68,yy,16);label(name,x+101,yy)
    return h
def note(lines,x,y,dy=27):
    for i,s in enumerate(lines):txt(s,x,y+i*dy,17,'#735223')
def begin(title,index):
    global svgs
    svgs=['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1100" viewBox="0 0 1600 1100">','<rect width="1600" height="1100" fill="white"/>']
    pdf.saveState();pdf.scale(1122.52/W,793.70/H);pdf.translate(0,H);pdf.scale(1,-1)
    # Text is counter-flipped below, while geometric coordinates use top-left origin.
    txt('语音对讲首批5台 - '+title,45,52,31)
    txt('V1工程电路图；同名绿色网络标签电气相连；按引脚编号接线。',45,87,18)
    txt('询价/复核版本：PCB未布线，电源与机械未验证，暂不下单生产。',45,1034,18,'#9b4b16')
    txt('2026-11-19  /  '+str(index)+' of 5',1545,1070,17,anchor='end')
    line([(45,107),(1555,107)],'#aebdca',1)
def end(index):
    pdf.restoreState();pdf.showPage();svgs.append('</svg>');(OUT/f'电路图-{index:02d}.svg').write_text('\n'.join(svgs),encoding='utf-8')

# reportlab text must remain upright under the page's top-left transform.
original_txt=txt
def txt(s,x,y,size=19,color='#213547',anchor='start'):
    pdf.saveState();pdf.translate(x,y);pdf.scale(1,-1)
    pdf.setFont('Chinese',size);pdf.setFillColor(HexColor(color))
    if anchor=='middle':pdf.drawCentredString(0,0,s)
    elif anchor=='end':pdf.drawRightString(0,0,s)
    else:pdf.drawString(0,0,s)
    pdf.restoreState()
    svgs.append(f'<text x="{x}" y="{y}" font-family="SimHei,Microsoft YaHei,Arial,sans-serif" font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')

begin('外电、充电与电池温度',1)
section('输入/受保护电池/NTC',45,130,415,730)
connector('J1',65,182,370);connector('J2',65,330,370);connector('J4',65,478,370)
note(['J2接电池包保护输出，非裸电芯。','J4接电池上的10k NTC。','B值和电芯规格未冻结。','J1候选约5.2V；最终适配器待定。','暂用有限流台式电源验证。'],65,660)
section('充电IC与温度/充电电流设置',485,130,1070,730)
device('U1',720,180,360)
group_passives(['R1','R2','R3','C1','C2','C12'],550,560,2,500,110)
note(['R1=2.7k：按TPOWER手册约0.407A充电；更换品牌须重算。',
      '温度网络：VIN_EXT - R2 - TEMP - R3 - NTC - 电池10k NTC - GND。',
      'U1散热焊盘与钢网、电池充电条件须工程复核。'],505,900)
end(1)

begin('电池升压与硬件欠压',2)
section('升压IC及主电感',45,130,1510,440)
device('U2',445,200,330)
passive('L1',1070,250);passive('C6',1070,385)
note(['VBAT - L1 - SW；C6连接CBST与SW。','SW是高频开关节点，不能长线绕行。','大电流铜皮/散热尚未完成设计。'],1000,465)
section('反馈和局部电容',45,590,930,330)
group_passives(['R4','R5','C3','C4','C5','C10'],75,700,3,300,135)
section('独立电池欠压保护',995,590,560,330)
device('U4',1150,650,215,2)
passive('R6',1050,865)
note(['反馈BOOST5V - R4 - BOOST_FB - R5 - GND；PWM典型约5.15V。',
      'C4/C5须核直流偏压有效容量；U4标称3.08V/200ms，低电量回弹重复启动待测。'],450,957)
end(2)

begin('外电/电池自动切换与比较器',3)
section('电源切换器',45,130,690,380)
device('U3',240,195,280)
section('外电比较器与控制供电',755,130,800,380)
device('U5',965,195,300)
section('控制电源二极管与基准',45,530,690,400)
device('D1',240,592,260,2);device('U6',240,780,260,2)
section('分压、迟滞、偏置与电容',755,530,800,460)
group_passives(['R7','R8','R9','R10','R11','C7','C8','C9','C11'],790,625,3,250,125,220)
note(['MODE接VCTL，PR1接PRIORITY；外电优先切换由硬件控制。',
      'VCTL由D1两路低电流供电，D1不承载系统大电流。',
      '恢复/下降阈值、启动、切换压降与470uF浪涌须实测。'],65,950)
end(3)

begin('电量/外电检测、状态与按钮',4)
section('ADC分压与滤波',45,130,1510,330)
group_passives(['R12','R13','C13','R14','R15','C14'],80,245,3,470,125)
note(['ADC_BAT = VBAT / 2；ADC_EXT = VIN_EXT x 0.4。ADC GPIO未分配，固件待适配。'],80,433)
section('3.3V上拉状态输出',45,480,695,390)
group_passives(['R16','R17','R18'],85,585,1,0,110)
note(['MUX_ST、CHRG、DONE仅用3.3V上拉。'],80,900)
section('常开自复位呼叫按钮',760,480,795,455)
connector('J10',785,542,320);connector('JP1',1145,542,380)
passive('R19',795,785);passive('C15',1170,785)
note(['按钮两端接BTN/GND。JP1：1-2选GPIO0，2-3选GPIO9。',
      '推荐避开GPIO0启动绑带；GPIO9和明确按下/消抖需固件适配。',
      '当前固件不是直接匹配新按钮电路，不由贴片商家自行更改。'],785,866)
end(4)

begin('模块连接与可选雷达',5)
section('ESP32线束；非开发板直插座',45,130,475,830)
connector('J5',65,177,435)
section('已验证模块的板级接线',540,130,1015,800)
connector('J3',565,177,410);connector('J6',1040,177,490)
connector('J7',565,380,410);connector('J8',1040,380,490)
connector('J9',565,635,410);connector('JP2',1040,635,490)
passive('C16',1055,860)
for i,ref in enumerate(['TP1','TP2']):
    record(ref);label(ref+' '+parts[ref]['pins']['1'],70+i*190,960)
note(['J6：ESP TX17→4G RX，ESP RX18←4G TX；IO4→DTR；4G板输入与UART电平须核对。',
      'J7：BCLK14/WS13/DATA12；J8：BCLK15/WS16/DATA7；其余音频模块焊盘沿用原样机。',
      'J9：雷达TX→GPIO6，雷达RX←预留GPIO8；JP2短接才给雷达供电，基础款不装雷达。',
      '喇叭接MAX98357的两路差分输出，任一端都不接GND；开发板USB与底板供电隔离待核。'],550,944,24)
end(5)
pdf.save()
assert drawn=={r:p['pins'] for r,p in parts.items()}, {'missing':set(parts)-set(drawn),'extra':set(drawn)-set(parts)}
(OUT/'电路图核对.json').write_text(json.dumps({'diagram_components':len(drawn),'named_pins':sum(bool(n) for p in drawn.values() for n in p.values()),'matches_design_json':True,'SMT_per_board':42,'THT_per_board':13,'production_ready':False,'reason':'PCB未布线/设计与实物验证未完成'},ensure_ascii=False,indent=2),encoding='utf-8')

request='''您好，我需要做5台ESP32-S3＋自研ML307 4G语音对讲工程样机。现有通话已跑通，首版保留开发板、4G板、INMP441麦克风板、MAX98357功放板和喇叭，新增一块连接/充电备用电源底板。

底板每块：42个SMT元件＋13个插件。5块净需求：210个SMT元件＋65个插件。Excel的额外备料单列，请分别报材料、损耗和加工，不把备料当成每板安装量。

SMT主要型号：TPOWER TP4056、TI TPS61230ARNSR、TPS2117DRLR、TLV803EA30DBZR、LM393DR、TL431BIDBZR，Nexperia BAT54C,215、Sunlord SWPA6045S1R0NT，以及19个0603电阻、15个贴片电容。插件为12个排针/接线端子和1个470uF电解电容。详细位号、封装和数量见Excel/CSV。

目前提供的是工程原理图和未布线的PCB摆放草图，不是生产文件；90×65mm板框、外壳、部分采购料号、电源保护/切换和装盒性能尚未冻结。

请先确认贵店是否能完成硬件设计复核、电源大电流布局布线和实物调试；如果只做SMT，请只报代采/贴片/插件焊接能力与费用，待最终生产文件后加工。

请分项报价：
1. 电源/接口原理图复核、完整PCB设计，包含封装/钢网检查和可编辑KiCad工程；明确修改轮次及调试范围。
2. 5块PCB裸板加工，确认最终板尺寸、层数/板厚/铜厚、交期。
3. 元件代采净用量及额外备料，Excel中填实际品牌料号和单价；替代料先确认。
4. 钢网/开机、SMT按台工费、插件焊接、首件检查、返修以及税运。
5. 如可提供：空载/目标5V2A带载、充电、电源切换的测试及记录费用，仪器和电池条件注明。

电池、适配器、外壳/支架另行选型；可选雷达只保留接口，基础5台不采购5块雷达。自研4G板和已验证模块不由通用淘宝板自动替换。固件协议和通话链路按现有工程保留，不属于贴片商家自行变更范围。

请不要按当前草图直接制板或代购全部待确认器件。最终BOM、布线、结构和文件检查完成后再安排生产。
'''
(OUT/'发淘宝商家的询价说明.txt').write_text(request,encoding='utf-8')
md=['# 语音对讲首批5台采购与贴片询价','',
 '日期：2026-11-19。当前是工程询价资料；PCB尚未布线，未发布可下单Gerber、钢网和坐标文件。请先取得设计复核与加工分项报价。','',
 '## 商家要贴什么','',
 '| 内容 | 每块底板 | 5块净用量 |','| --- | ---: | ---: |',
 '| SMT贴片 | 42个 | 210个 |','| 插件焊接 | 13个 | 65个 |',
 '| 测试点TP1/TP2、安装孔H1～H4 | 板上焊盘/孔 | 不采购零件 |','',
 'SMT构成：6颗IC＋1颗双二极管＋1颗电感＋19个电阻＋15个贴片电容。插件构成：12个排针/端子＋1个电解电容。','',
 'Excel中“额外备料”是独立建议，不是每板装配数量；按商家供料/飞达损耗要求调整并单独报价。净用量与备料不要重复算。','',
 '## 底板逐项清单','',
 '| 工艺 | 位号 | 型号/数值 | 封装 | 每板 | 5板净用量 |','| --- | --- | --- | --- | ---: | ---: |']
for r in rows:md.append(f'| {r["category"]} | {",".join(r["refs"])} | {r["model"]} | {r["package"]} | {r["unit"]} | {r["required5"]} |')
md+=['','0603指英制0603/公制1608，0805指英制0805/公制2012。电阻未标0.1%的按1%询价。贴片电容按≥10V、X5R/X7R询价，C4/C5必须核对约5.15V直流偏压有效容量，不能仅因标22uF就认定可用。','',
 '## 另外采购与组装，不让商家当成芯片贴在底板上','',
 '| 部件 | 首批数量 | 采购要求 |','| --- | ---: | --- |']
for r in modules:md.append(f'| {r["item"]} | {r["required5"]} | {r["spec"]}；{r["note"]} |')
md+=['','已有可用零件按实物库存扣减。原约60元基础套件包含ESP32、4G、天线、音频和喇叭等，不在预算中重复相加。外购模块表尚未填写库存与报价时，不用空白自动代表0库存或0元。','',
 '## 下单前必须关闭的确认项','',
 '| 项目 | 当前具体缺口 | 下一步 |','| --- | --- | --- |',
 '| PCB | 未布线；132处未连接 | 完成大电流/散热/地平面、完整DRC和装配检查，再生成生产文件 |',
 '| 核心封装 | U1散热焊盘；U2非对称焊盘/阻焊/钢网；U3封装 | 按原厂和实际采购料号复核，不能只对脚数 |',
 '| 电池与温度 | 具体电芯、保护、线、接头、尺寸、NTC B值未定 | 提供≥5A持续放电目标/充电规格，重新核温度窗口和低电量恢复 |',
 '| 适配器/电源性能 | 候选约5.2V/3A；恢复阈值、容差、线路压降和雷达纹波未验证 | 固定可采购型号或调整支路电路，不能买差不多电压替代 |',
 '| 电容与端子 | 部分只有通用封装和参数；C9高度/ESR，端子外形未定 | 商家填准确料号/尺寸图/参数后确认再采购 |',
 '| 保护和USB | 输入/输出保护、误接及开发板电脑USB倒灌隔离未冻结 | 硬件工程师完成方案；电气测试用有限流电源 |',
 '| GPIO与固件 | 按钮输入/消抖、ADC/状态GPIO未定，省电关断未完成 | 本项目适配和回归，通信协议保持当前约束 |',
 '| 外壳与模块 | 板框90x65mm暂定，模块/喇叭/外壳空间未核对 | 量实物、内部布局、确定安装孔再冻结板框 |','',
 '## 提供给商家的文件','',
 '- [Excel清单](首批5台采购与贴片询价清单.xlsx)：分“PCB贴片与插件”和“整机外购模块”，可填实际料号、报价和已有数量。',
 '- [CSV清单](首批5台贴片及插件询价清单.csv)：UTF-8 BOM编码，可导入商家工具。',
 '- [电路图PDF](首批5台语音对讲电路图.pdf)：5页，覆盖充电/温度、升压/欠压、切换、检测/按钮、模块接口。绿色同名网络标签相连；不是板上物理线长示意。',
 '- [询价文字](发淘宝商家的询价说明.txt)：可直接复制给商家。',
 '- 原可编辑KiCad原理图、未布线PCB、本地符号/封装库随资料包提供给负责设计的人员。','',
 '此清单按当前设计表核对：55个需安装实物/板，57个位号含2个无采购测试点。图片/PDF与设计表的171个命名引脚网络一致；这种核对不代表电路或供电已实测。','',
 '## 费用询价口径','',
 '原约1000元是首批5台物料和部分加工预算，非完整开发总价。本次商家报价须分别列元件、净用量/备料、裸板、开机/钢网、SMT、插件、设计复核/布线、实物调试、税运。最终核心保护、适配器、电池等选型若变化，BOM和预算同步更新。','',
 '初步电源芯片选型资料见工程根目录“首版PCB与备用电源选型.md”，连接说明见hardware/voice_carrier_v1/README.md。',
 '当前阶段先确认商家能力和报价，工程设计完成后再制板。']
(OUT/'首批5台采购与商家询价.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
print('Built supplier lists and 5-sheet circuit PDF; all',len(drawn),'reference pin maps included')
