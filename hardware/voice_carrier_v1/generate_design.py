"""Build the reproducible KiCad carrier prototype. Run with KiCad's Python."""
from pathlib import Path
import json, math, csv, uuid, shutil, os
import pcbnew as pcb

ROOT=Path(__file__).resolve().parent
LIB=Path(os.environ.get('KICAD9_FOOTPRINT_DIR', str(ROOT.parents[1]/'build/cad-tools/kicad/share/kicad/footprints')))
OUT=ROOT/'exports'
OUT.mkdir(exist_ok=True)
LOCAL=ROOT/'Voice.pretty'
LOCAL.mkdir(exist_ok=True)
board=pcb.BOARD()
io=pcb.PCB_IO_MGR.PluginFind(pcb.PCB_IO_MGR.KICAD_SEXP)
mm=pcb.FromMM
v=lambda x,y:pcb.VECTOR2I(mm(x),mm(y))
nets={}
def net(name):
    if name not in nets:
        n=pcb.NETINFO_ITEM(board,name,len(nets)+1);board.Add(n);nets[name]=n
    return nets[name]
parts=[]

def custom(name,pads,w,h):
    fp=pcb.FOOTPRINT(board)
    fp.SetFPID(pcb.LIB_ID('Voice',name))
    for number,x,y,sx,sy in pads:
        pd=pcb.PAD(fp);pd.SetNumber(str(number));pd.SetAttribute(pcb.PAD_ATTRIB_SMD)
        pd.SetShape(pcb.PAD_SHAPE_RECT);pd.SetSize(v(sx,sy));pd.SetPosition(v(x,y))
        layers=pcb.LSET()
        for layer in [pcb.F_Cu,pcb.F_Paste,pcb.F_Mask]:layers.AddLayer(layer)
        pd.SetLayerSet(layers);fp.Add(pd)
    for a,b in [((-w/2,-h/2),(w/2,-h/2)),((w/2,-h/2),(w/2,h/2)),((w/2,h/2),(-w/2,h/2)),((-w/2,h/2),(-w/2,-h/2))]:
        sh=pcb.PCB_SHAPE(fp);sh.SetShape(pcb.SHAPE_T_SEGMENT);sh.SetStart(v(*a));sh.SetEnd(v(*b));sh.SetWidth(mm(.05));sh.SetLayer(pcb.F_CrtYd);fp.Add(sh)
    io.FootprintSave(str(LOCAL),fp)
    return fp

# These two asymmetric footprints are replaced below only after the TI land
# patterns have been transcribed. Never substitute a regular QFN footprint.
def add(ref,value,footprint,x,y,pin_nets,angle=0,source='',price=.02,kind='pcb'):
    lib,name=footprint.split(':')
    fp=io.FootprintLoad(str(LOCAL if lib=='Voice' else LIB/(lib+'.pretty')),name,False)
    if fp is None:raise RuntimeError('Missing footprint '+footprint)
    fp.SetReference(ref);fp.SetValue(value);fp.SetPosition(v(x,y));fp.SetOrientationDegrees(angle)
    for pd in fp.Pads():
        num=pd.GetNumber()
        if num in pin_nets and pin_nets[num]:pd.SetNet(net(pin_nets[num]))
    fp.Reference().SetTextSize(v(.7,.7));fp.Reference().SetTextThickness(mm(.12))
    fp.Value().SetVisible(False)
    board.Add(fp)
    parts.append(dict(ref=ref,value=value,footprint=footprint,pins=pin_nets,x=x,y=y,angle=angle,source=source,price=price,kind=kind))
    return fp

def r(ref,val,x,y,a,b,angle=0,price=.02):
    return add(ref,val,'Resistor_SMD:R_0603_1608Metric',x,y,{'1':a,'2':b},angle,price=price)
def c(ref,val,x,y,a,b,angle=0,price=.06,large=False):
    return add(ref,val,'Capacitor_SMD:C_0805_2012Metric' if large else 'Capacitor_SMD:C_0603_1608Metric',x,y,{'1':a,'2':b},angle,price=price)
def hdr(ref,label,x,y,names,angle=0):
    return add(ref,label,f'Connector_PinHeader_2.54mm:PinHeader_1x{len(names):02d}_P2.54mm_Vertical',x,y,{str(i+1):s for i,s in enumerate(names)},angle,price=.15+len(names)*.025)
def terminal(ref,label,x,y,names):
    return add(ref,label,'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal',x,y,{'1':names[0],'2':names[1]},price=1.2)
def txt(s,x,y,size=1,layer=pcb.F_SilkS):
    size=max(size,.8)
    t=pcb.PCB_TEXT(board);t.SetText(s);t.SetPosition(v(x,y));t.SetTextSize(v(size,size));t.SetTextThickness(mm(.15));t.SetLayer(layer);board.Add(t)

def design():
    # Main input, battery and 4G power are screw terminals; signal headers are
    # harness interfaces, NOT guessed sockets for the physical modules.
    terminal('J1','5.2V INPUT',13,8,['VIN_EXT','GND'])
    terminal('J2','1S BATTERY',13,56,['VBAT','GND'])
    terminal('J3','4G POWER',73,8,['SYS5V','GND'])
    hdr('J4','BAT NTC',26,57,['NTC','GND'],90)
    esp=['SYS5V','GND','V3V3','GND','IO17','IO18','IO4','IO14','IO13','IO12','IO15','IO16','IO7','IO6','IO8','IO0','IO9','ADC_BAT','ADC_EXT','MUX_ST','CHRG','DONE','IO43','IO44']
    add('J5','ESP32 HARNESS','Connector_PinHeader_2.54mm:PinHeader_2x12_P2.54mm_Vertical',56,14,{str(i+1):n for i,n in enumerate(esp)},price=.8)
    hdr('J6','4G UART',73,20,['GND','IO17','IO18','IO4'],90)
    hdr('J7','INMP441',73,33,['V3V3','GND','IO14','IO13','IO12'],90)
    hdr('J8','MAX98357',73,46,['SYS5V','GND','IO15','IO16','IO7'],90)
    hdr('J9','RADAR OPTIONAL',54,56,['RADAR5V','GND','IO6','IO8'],90)
    hdr('J10','CALL BUTTON',81,53,['BTN','GND'],90)
    hdr('JP1','BUTTON IO0 / IO9',72,56,['IO0','BTN','IO9'],90)
    hdr('JP2','RADAR POWER',43,56,['SYS5V','RADAR5V'],90)
    r('R1','2.7k',17,20,'CHG_PROG','GND')
    r('R2','9.1k',8,24,'VIN_EXT','TEMP')
    r('R3','3.3k',8,29,'TEMP','NTC')
    add('U1','TP4056 TPOWER','Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm',16,27,{'1':'TEMP','2':'CHG_PROG','3':'GND','4':'VIN_EXT','5':'VBAT','6':'DONE','7':'CHRG','8':'VIN_EXT','9':'GND'},source='https://item.szlcsc.com/354934.html',price=.4012)
    c('C1','10u 10V',23.5,24,'VIN_EXT','GND',large=True,price=.15)
    c('C2','10u 10V',23.5,30,'VBAT','GND',large=True,price=.15)
    add('U2','TPS61230ARNSR','Voice:TI_RNS0007A',33,30,{'1':'CBST','2':'BOOST_EN','3':'BOOST_FB','4':'VBAT','5':'SW','6':'GND','7':'BOOST5V'},180,source='https://item.szlcsc.com/348561.html',price=3.14)
    add('L1','SWPA6045S1R0NT','Inductor_SMD:L_Sunlord_SWPA6045S',32,24,{'1':'VBAT','2':'SW'},-90,source='https://item.szlcsc.com/98160.html',price=.335)
    c('C3','22u 10V',38.2,22.5,'VBAT','GND',large=True,price=.2)
    c('C4','22u 10V',37,28.5,'BOOST5V','GND',large=True,price=.2)
    c('C5','22u 10V',39.5,32,'BOOST5V','GND',90,large=True,price=.2)
    c('C6','10n',30,29,'CBST','SW',price=.04)
    r('R4','331k 0.1%',36,35,'BOOST5V','BOOST_FB',price=.08)
    r('R5','100k 0.1%',36,38,'BOOST_FB','GND',price=.08)
    add('U3','TPS2117DRLR','Voice:TI_DRL0008A',43,20,{'1':'GND','2':'SYS5V','3':'VIN_EXT','4':'PRIORITY','5':'VCTL','6':'BOOST5V','7':'SYS5V','8':'MUX_ST'},source='https://item.szlcsc.com/24017237.html',price=1.82)
    c('C7','1u',43,15,'VIN_EXT','GND')
    c('C8','1u',46,23,'BOOST5V','GND')
    add('C9','470u 10V LOW ESR','Capacitor_THT:CP_Radial_D8.0mm_P3.50mm',47,34,{'1':'SYS5V','2':'GND'},price=1)
    # Independent battery undervoltage disables only boost, never external input.
    add('U4','TLV803EA30DBZR','Package_TO_SOT_SMD:SOT-23',27,41,{'1':'GND','2':'BOOST_EN','3':'VBAT'},source='https://item.szlcsc.com/5914664.html',price=1.57)
    r('R6','100k',23,38,'VBAT','BOOST_EN')
    c('C10','100n',24,44,'VBAT','GND')
    # Accurate external-priority comparator + 0.5% reference, hysteresis.
    # Control supply diode OR is low-current only, not the system power path.
    add('D1','BAT54C,215','Package_TO_SOT_SMD:SOT-23',10,39,{'1':'VIN_EXT','2':'BOOST5V','3':'VCTL'},source='https://item.szlcsc.com/38684.html',price=.044)
    add('U5','LM393DR','Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',15,46,{'1':'PRIORITY','2':'REF2V5','3':'EXT_SENSE','4':'GND','5':'GND','6':'REF2V5','7':'','8':'VCTL'},source='https://item.szlcsc.com/68565.html',price=.1941)
    add('U6','TL431BIDBZR','Package_TO_SOT_SMD:SOT-23',8,46,{'1':'REF2V5','2':'REF2V5','3':'GND'},source='https://item.szlcsc.com/42267.html',price=.2337)
    r('R7','1.8k',7,42,'VCTL','REF2V5')
    r('R8','105k 0.1%',17,37,'VIN_EXT','EXT_SENSE',price=.08)
    r('R9','100k 0.1%',17,40,'EXT_SENSE','GND',price=.08)
    r('R10','5.6M 1%',22,47,'PRIORITY','EXT_SENSE')
    r('R11','10k',23,51,'VCTL','PRIORITY')
    c('C11','100n',8,50,'VCTL','GND')
    c('C12','100n',12,35,'VIN_EXT','GND')
    # Separate ADC measurements of protected battery and unswitched input.
    r('R12','100k 1%',35,44,'VBAT','ADC_BAT')
    r('R13','100k 1%',39,44,'ADC_BAT','GND')
    c('C13','100n',43,44,'ADC_BAT','GND')
    r('R14','150k 1%',35,48,'VIN_EXT','ADC_EXT')
    r('R15','100k 1%',39,48,'ADC_EXT','GND')
    c('C14','100n',43,48,'ADC_EXT','GND')
    for ref,y,n in [('R16',18,'MUX_ST'),('R17',22,'CHRG'),('R18',26,'DONE')]:
        r(ref,'10k',51,y,'V3V3',n)
    r('R19','10k',79,49,'V3V3','BTN')
    c('C15','100n',84,49,'BTN','GND')
    c('C16','10u 10V',79,37,'RADAR5V','GND',large=True,price=.15)
    for ref,x,y,n in [('TP1',64,10,'IO43'),('TP2',67,10,'IO44')]:
        add(ref,n,'TestPoint:TestPoint_Pad_D1.5mm',x,y,{'1':n},price=0)
    # Four generic holes. They are NOT claimed to match the purchased enclosure.
    for ref,x,y in [('H1',4,4),('H2',86,4),('H3',4,61),('H4',86,61)]:
        add(ref,'M3','MountingHole:MountingHole_3.2mm_M3',x,y,{},price=0,kind='mechanical')
    for a,b in [((0,0),(90,0)),((90,0),(90,65)),((90,65),(0,65)),((0,65),(0,0))]:
        sh=pcb.PCB_SHAPE(board);sh.SetShape(pcb.SHAPE_T_SEGMENT);sh.SetStart(v(*a));sh.SetEnd(v(*b));sh.SetLayer(pcb.Edge_Cuts);sh.SetWidth(mm(.05));board.Add(sh)
    txt('VOICE INTERCOM - V1 PLACEMENT DRAFT',45,3,1)
    txt('90 x 65 mm / 2 LAYERS',45,6,.8)
    txt('J9 OPTIONAL 24G / 60G RADAR',45,61,.8)
    txt('1=5V  2=GND  3=RADAR TX  4=RADAR RX',45,63,.6)
    txt('POWER: target 5V 2A / BAT 1S 4.2V',32,11,.65)
    txt('INPUT: 5.2V regulated',15,14,.65)
    for s,x,y in [('4G UART',76,17),('MIC 3V3',76,30),('AMP 5V',76,43),('ESP32 HARNESS',60,47),('CALL',82,60)]:txt(s,x,y,.7)
    for fp in board.GetFootprints():
        fp.Reference().SetLayer(pcb.F_Fab)
        fp.Reference().SetTextSize(v(.8,.8))
        fp.Reference().SetVisible(True)
    pcb.SaveBoard(str(ROOT/'voice_carrier_v1.kicad_pcb'),board)
    (ROOT/'design.json').write_text(json.dumps({'revision':'V1-PLACEMENT-DRAFT','status':'Unrouted engineering draft; mechanical dimensions and power performance NOT verified','dimensions_mm':[90,65],'parts':parts,'input_spec':'Regulated approximately 5.2V; <=5.5V; required minimum and exact adapter remain to be validated','radar_optional':True},ensure_ascii=False,indent=2),encoding='utf-8')
    with (ROOT/'pcb-bom.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['Reference','Value','Footprint','Qty','Reference CNY','Source','Status'])
        for p in parts:w.writerow([p['ref'],p['value'],p['footprint'],1,p['price'],p['source'],'reference/estimate; prototype'])
    print('Created',len(parts),'parts',len(nets),'nets',flush=True)

if __name__=='__main__':
    land=json.loads((ROOT/'ti-landpatterns.json').read_text(encoding='utf-8'))
    for name,settings in land.items():custom(name,settings['pads'],settings['courtyard'][0],settings['courtyard'][1])
    design()
