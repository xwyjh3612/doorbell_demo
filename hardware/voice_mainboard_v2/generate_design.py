"""KiCad 9 placement draft: soldered ML307R-DL, existing ESP/audio, UPS reserved.

Run with build/cad-tools/kicad/bin/python.exe. No production plots are made.
"""
from pathlib import Path
import json, os
import pcbnew as pcb

ROOT = Path(__file__).resolve().parent
PROJECT = 'voice_mainboard_v2'
LIB = Path(os.environ.get('KICAD9_FOOTPRINT_DIR', str(ROOT.parents[1]/'build/cad-tools/kicad/share/kicad/footprints')))
LOCAL = ROOT/'VoiceV2.pretty'
LOCAL.mkdir(exist_ok=True)
(ROOT/'exports').mkdir(exist_ok=True)
board = pcb.BOARD()
io = pcb.PCB_IO_MGR.PluginFind(pcb.PCB_IO_MGR.KICAD_SEXP)
mm = pcb.FromMM
v = lambda x,y: pcb.VECTOR2I(mm(x),mm(y))
nets, parts = {}, []

def net(name):
    if name not in nets:
        n=pcb.NETINFO_ITEM(board,name,len(nets)+1);board.Add(n);nets[name]=n
    return nets[name]

def line(parent,a,b,layer=pcb.F_Fab,width=.1):
    sh=pcb.PCB_SHAPE(parent);sh.SetShape(pcb.SHAPE_T_SEGMENT)
    sh.SetStart(v(*a));sh.SetEnd(v(*b));sh.SetWidth(mm(width));sh.SetLayer(layer);parent.Add(sh)

def rectangle(parent,w,h,layer=pcb.F_CrtYd):
    for a,b in [((-w/2,-h/2),(w/2,-h/2)),((w/2,-h/2),(w/2,h/2)),((w/2,h/2),(-w/2,h/2)),((-w/2,h/2),(-w/2,-h/2))]:line(parent,a,b,layer,.05)

def ml307_footprint():
    # Manufacturer Fig.3 pin numbering + Fig.20 TOP-side recommended land pattern.
    # 44 ordinary perimeter pins, 4 extra perimeter pads 95..98, 61 internal pads.
    pads=[]
    for i in range(13):pads.append((i+1,-7.9,-6.6+i*1.1,2.6,.6))
    for i,n in enumerate([95,*range(14,23),96]):pads.append((n,-5.5+i*1.1,8.85,.6,2.6))
    for i in range(13):pads.append((23+i,7.9,6.6-i*1.1,2.6,.6))
    for i,n in enumerate([98,44,43,42,41,40,39,38,37,36,97]):pads.append((n,-5.5+i*1.1,-8.85,.6,2.6))
    for i,n in enumerate([99,45,46,47,48,49,50,51,52,53,100]):pads.append((n,-5,-6+i*1.2,1,.7))
    for i,n in enumerate([104,67,66,65,64,63,62,61,60,59,103]):pads.append((n,5,-6+i*1.2,1,.7))
    for i,n in enumerate([106,72,71,70,69,68,105]):pads.append((n,-3.6+i*1.2,-6,.7,1))
    for i,n in enumerate([101,54,55,56,57,58,102]):pads.append((n,-3.6+i*1.2,6,.7,1))
    for i,n in enumerate([73,74,75,76,77,78,79,80]):pads.append((n,-3.2,-4.2+i*1.2,1,.7))
    for i,n in enumerate([88,87,86,85,84,83,82,81]):pads.append((n,3.2,-4.2+i*1.2,1,.7))
    for i,n in enumerate([89,90,91]):pads.append((n,-.9,-1.8+i*1.8,1.3,1.3))
    for i,n in enumerate([94,93,92]):pads.append((n,.9,-1.8+i*1.8,1.3,1.3))
    for i,n in enumerate([107,108,109]):pads.append((n,-1.2+i*1.2,4.2,.7,1))
    assert len(pads)==109 and {p[0] for p in pads}==set(range(1,110))
    fp=pcb.FOOTPRINT(board);fp.SetFPID(pcb.LIB_ID('VoiceV2','ML307R_DL_109_15.8x17.7mm_DRAFT'))
    for n,x,y,sx,sy in pads:
        p=pcb.PAD(fp);p.SetNumber(str(n));p.SetAttribute(pcb.PAD_ATTRIB_SMD)
        p.SetShape(pcb.PAD_SHAPE_OVAL if n<=44 or 95<=n<=98 else pcb.PAD_SHAPE_RECT)
        p.SetSize(v(sx,sy));p.SetPosition(v(x,y))
        layers=pcb.LSET()
        for layer in [pcb.F_Cu,pcb.F_Paste,pcb.F_Mask]:layers.AddLayer(layer)
        p.SetLayerSet(layers);fp.Add(p)
    rectangle(fp,15.8,17.7,pcb.F_Fab)
    rectangle(fp,21.8,23.7)  # 3 mm component clearance from module body.
    line(fp,(-9.6,-7.5),(-9.6,-6.0),pcb.F_SilkS,.2)
    fp.SetLibDescription('TOP-side manufacturer land pattern transcription; supplier CAD and stencil approval pending. No 3D body model.')
    io.FootprintSave(str(LOCAL),fp)
    (ROOT/'ml307-landpattern.json').write_text(json.dumps({'source':'ML307R Hardware Design AT V1.0.1, Fig.3 p19 and Fig.20 p56','source_url':'https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/M307R_Hardware_Datasheet.pdf','view':'PCB TOP, NOT module bottom','body_mm':[15.8,17.7,2.2],'land_extent_mm':[18.4,20.3],'pads':pads,'release':'DRAFT: supplier CAD/physical overlay/stencil confirmation required'},indent=2),encoding='utf-8')

def add(ref,value,footprint,x,y,pins,group,angle=0,names=None,dnp=False,source='',note=''):
    lib,name=footprint.split(':')
    fp=io.FootprintLoad(str(LOCAL if lib=='VoiceV2' else LIB/(lib+'.pretty')),name,False)
    if fp is None:raise RuntimeError(footprint)
    fp.SetReference(ref);fp.SetValue(value);fp.SetPosition(v(x,y));fp.SetOrientationDegrees(angle)
    for pd in fp.Pads():
        n=pd.GetNumber()
        if pins.get(n):pd.SetNet(net(pins[n]))
    fp.Reference().SetLayer(pcb.F_Fab);fp.Reference().SetTextSize(v(.75,.75));fp.Reference().SetTextThickness(mm(.12))
    fp.Value().SetVisible(False);board.Add(fp)
    parts.append(dict(ref=ref,value=value,footprint=footprint,pins=pins,names=names or {},x=x,y=y,angle=angle,group=group,dnp=dnp,source=source,note=note,kind='mechanical' if ref.startswith('H') else 'pcb'))
    return fp

def r(ref,value,x,y,a,b,g,angle=0,dnp=False):return add(ref,value,'Resistor_SMD:R_0603_1608Metric',x,y,{'1':a,'2':b},g,angle,dnp=dnp)
def c(ref,value,x,y,a,b,g,angle=0,dnp=False,big=False):return add(ref,value,'Capacitor_SMD:C_0805_2012Metric' if big else 'Capacitor_SMD:C_0603_1608Metric',x,y,{'1':a,'2':b},g,angle,dnp=dnp)
def hdr(ref,value,x,y,signals,g,angle=0):return add(ref,value,f'Connector_PinHeader_2.54mm:PinHeader_1x{len(signals):02d}_P2.54mm_Vertical',x,y,{str(i+1):s for i,s in enumerate(signals)},g,angle)
def mos(ref,value,x,y,gate,source,drain,g):return add(ref,value,'Package_TO_SOT_SMD:SOT-23',x,y,{'1':gate,'2':source,'3':drain},g,names={'1':['G','input'],'2':['S','passive'],'3':['D','passive']})
def tp(ref,value,x,y,n,g):return add(ref,value,'TestPoint:TestPoint_Pad_D1.0mm',x,y,{'1':n},g)

def design():
    g='01 UPS / BATTERY / SYSTEM'
    add('J1','DC 5.5x2.5mm CENTER POSITIVE 5V','Connector_BarrelJack:BarrelJack_Wuerth_694108106102_2.5x5.5mm',9,8,{'1':'VIN_EXT_5V','2':'GND','3':''},g,names={'1':['CENTER_PLUS','passive'],'2':['SLEEVE_GND','passive'],'3':['SW_UNUSED','passive']},note='2.5mm inner / 5.5mm outer assumption. Exact low-cost purchased socket footprint must match; Wuerth geometry is a draft candidate, not mandatory purchase.')
    hdr('J2','UPS INPUT TO DAUGHTERBOARD',8,15,['VIN_EXT_5V','GND'],g,90)
    hdr('J3','UPS STABLE 5V RETURN',8,53,['SYS_5V','GND'],g,90)
    hdr('J4','1S BATTERY SENSE ONLY',8,60,['BAT_SENSE_IN','GND'],g,90)
    hdr('J5','UPS STATUS RESERVED 3V3 ONLY',15,53,['CHRG_OD','DONE_OD','UPS_PG_OD','GND'],g,90)
    hdr('JP1','BENCH BYPASS UPS - REMOVE WITH UPS',15,8,['VIN_EXT_5V','SYS_5V'],g,90)
    c('C1','22u 10V',20,8,'SYS_5V','GND',g,big=True)
    c('C2','100n',24,8,'SYS_5V','GND',g)
    # No invented UPS-chip footprint or battery current path. Sense wires only.
    # Bare modem needs a separate buck; it must NEVER be connected to 5V.
    g='02 MODEM 3.8V BUCK / DECOUPLING'
    add('U2','TPS563201DDCR CANDIDATE','Package_TO_SOT_SMD:SOT-23-6',42,8,{'1':'GND','2':'BUCK_SW','3':'SYS_5V','4':'BUCK_FB','5':'BUCK_EN','6':'BUCK_BST'},g,names={'1':['GND','power_in'],'2':['SW','passive'],'3':['VIN','power_in'],'4':['VFB','input'],'5':['EN','input'],'6':['VBST','passive']},source='https://www.ti.com/lit/ds/symlink/tps563201.pdf',note='3A candidate, minimum input 4.5V. Not the UPS PMIC; output/current/thermal validation pending.')
    r('R1','100k',35,8,'SYS_5V','BUCK_EN',g)
    c('C3','100n BST',43,4.5,'BUCK_BST','BUCK_SW',g)
    c('C4','22u 10V',36,4.5,'SYS_5V','GND',g,big=True)
    c('C5','22u 10V',31,4.5,'SYS_5V','GND',g,big=True)
    add('L1','2.2uH Isat>=4.5A DCR<50mOhm','Inductor_SMD:L_Sunlord_SWPA6045S',49,6.5,{'1':'BUCK_SW','2':'MODEM_3V8'},g,90,note='Footprint candidate; procure exact inductor before routing.')
    c('C6','22u 10V',51,12,'MODEM_3V8','GND',g,big=True)
    c('C7','22u 10V',46,12,'MODEM_3V8','GND',g,big=True)
    r('R2','39.2k 0.1%',39,13,'MODEM_3V8','BUCK_FB',g)
    r('R3','10k 0.1%',34,13,'BUCK_FB','GND',g)
    for ref,x in [('C8',59),('C9',73)]:
        add(ref,'220u 6.3V LOW ESR <=100mOhm','Capacitor_SMD:CP_Elec_6.3x5.8',x,6,{'1':'MODEM_3V8','2':'GND'},g,note='Transient reservoir per module guide; exact capacitor/ripple rating pending.')
    c('C10','10u 10V',65,7,'MODEM_3V8','GND',g,big=True)
    c('C11','100n',65,10,'MODEM_3V8','GND',g)
    c('C12','33p',69,10,'MODEM_3V8','GND',g)
    tp('TP1','MODEM VBAT',78,8,'MODEM_3V8',g)
    g='03 ML307R-DL / UART / CONTROL'
    ground={1,10,27,34,36,37,40,41,*range(45,49),*range(70,74),*range(88,96)}
    reserved={*range(2,7),8,26,*range(30,33),44,*range(50,59),*range(62,70),78,80,81,*range(83,86),*range(97,110)}
    functional={7:('PWR_ON_OFF','input'),9:('ADC0','input'),11:('USIM_DATA','bidirectional'),12:('USIM_RESET','output'),13:('USIM_CLK','output'),14:('USIM_PWR','power_out'),15:('RESET_N','input'),16:('NETLIGHT','output'),17:('UART0_RXD','input'),18:('UART0_TXD','output'),19:('UART0_DTR','input'),20:('UART0_RI','output'),21:('UART0_DCD','output'),22:('UART0_CTS','input'),23:('UART0_RTS','output'),24:('VDD_EXT','power_out'),25:('STATE','output'),28:('UART1_RXD','input'),29:('UART1_TXD','output'),33:('PCM_OUT','output'),35:('ANT_MAIN','passive'),38:('DBG_RXD','input'),39:('DBG_TXD','output'),42:('VBAT','power_in'),43:('VBAT','power_in'),49:('WAKEUPOUT','output'),59:('USB_DP','bidirectional'),60:('USB_DM','bidirectional'),61:('USB_VBUS','power_in'),74:('PWM0','output'),75:('PWM1','output'),76:('GPIO0','bidirectional'),77:('GPIO1','bidirectional'),79:('USIM_DET','input'),82:('BOOT_MODE','input'),86:('GPIO2','bidirectional'),87:('GPIO3','bidirectional'),96:('ADC1','input')}
    assert ground.isdisjoint(reserved) and ground|reserved|set(functional)==set(range(1,110))
    used={7:'MODEM_PWRKEY_N',11:'M_SIM_DATA',12:'M_SIM_RESET',13:'M_SIM_CLK',14:'SIM_VCC',15:'MODEM_RESET_N',16:'MODEM_NETLIGHT',17:'M_RX_1V8',18:'M_TX_1V8',19:'M_DTR_1V8',24:'MODEM_1V8',25:'MODEM_STATE_1V8',35:'RF_ANT',38:'DBG_RX_1V8',39:'DBG_TX_1V8',42:'MODEM_3V8',43:'MODEM_3V8',59:'M_USB_DP',60:'M_USB_DM',61:'USB_DETECT_5V',79:'SIM_DETECT',82:'MODEM_BOOT_N'}
    pins={str(n):'GND' if n in ground else used.get(n,'') for n in range(1,110)}
    names={str(n):['GND','power_in'] if n in ground else ['RSV_FLOAT','no_connect'] if n in reserved else list(functional[n]) for n in range(1,110)}
    add('U1','ML307R-DL SMT','VoiceV2:ML307R_DL_109_15.8x17.7mm_DRAFT',66,26,pins,g,names=names,source='https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/M307R_Hardware_Datasheet.pdf',note='All reserved pins float. Supplier footprint and stencil signoff pending.')
    for ref,y,a,b,direction in [('U3',19,'ESP_TX17','M_RX_1V8','ESP_3V3'),('U4',25,'ESP_RX18','M_TX_1V8','GND'),('U5',31,'ESP_DTR4','M_DTR_1V8','ESP_3V3')]:
        add(ref,'SN74AXC1T45DBVR','Package_TO_SOT_SMD:SOT-23-6',45,y,{'1':'ESP_3V3','2':'GND','3':a,'4':b,'5':direction,'6':'MODEM_1V8'},g,names={'1':['VCCA','power_in'],'2':['GND','power_in'],'3':['A','bidirectional'],'4':['B','bidirectional'],'5':['DIR','input'],'6':['VCCB','power_in']},source='https://www.ti.com/lit/ds/symlink/sn74axc1t45.pdf',note='Direction fixed per signal; power-off isolation. 921600 baud; never use slow I2C MOSFET shifter here.')
    for i,y in enumerate([19,25,31]):
        c(f'C{13+i*2}','100n',40,y,'ESP_3V3','GND',g)
        c(f'C{14+i*2}','100n',49,y,'MODEM_1V8','GND',g)
    r('R4','10k',40,35,'ESP_3V3','ESP_TX17',g)
    r('R5','100k',45,35,'ESP_DTR4','GND',g)
    mos('Q1','2N7002',52,43,'PWRKEY_CTL','GND','MODEM_PWRKEY_N',g)
    r('R6','100k',47,43,'PWRKEY_CTL','GND',g)
    hdr('J6','MANUAL PWRKEY HOLD 2-3.5s',55,48,['MODEM_PWRKEY_N','GND'],g,90)
    r('R7','4.7k AUTO ON LINK',60,43,'MODEM_PWRKEY_N','GND',g,dnp=True)
    mos('Q2','2N7002',65,43,'RESET_CTL','GND','MODEM_RESET_N',g)
    r('R8','100k',70,43,'RESET_CTL','GND',g)
    c('C19','10n',65,39.5,'MODEM_RESET_N','GND',g)
    hdr('J7','RESET SERVICE ONLY',68,48,['MODEM_RESET_N','GND'],g,90)
    hdr('J8','DOWNLOAD STRAP - OPEN NORMAL',81,45,['MODEM_BOOT_N','GND'],g,90)
    hdr('J9','MODEM DEBUG 1V8 ONLY',83,32,['GND','DBG_TX_1V8','DBG_RX_1V8','MODEM_1V8'],g)
    tp('TP2','STATE 1V8',80,23,'MODEM_STATE_1V8',g)
    tp('TP3','NETLIGHT 1V8',80,20,'MODEM_NETLIGHT',g)
    g='04 SIM / RF / USB SERVICE'
    add('J10','JAE SF72S006 SIM CANDIDATE','Connector_JAE:JAE_SIM_Card_SF72S006',77,55,{'C1':'SIM_VCC','C2':'SIM_RESET','C3':'SIM_CLK','C5':'GND','C6':'','C7':'SIM_DATA','CSW':'GND','DSW':'SIM_DETECT','SH':'GND'},g,names={'C1':['VCC','passive'],'C2':['RST','passive'],'C3':['CLK','passive'],'C5':['GND','passive'],'C6':['VPP_UNUSED','passive'],'C7':['IO','passive'],'CSW':['DETECT_COM','passive'],'DSW':['DETECT','passive'],'SH':['SHIELD','passive']},note='Candidate SIM socket; exact purchase model/card size/height to confirm. Keep SIM traces <150mm, preferably <50mm.')
    for ref,y,a,b in [('R9',49,'M_SIM_DATA','SIM_DATA'),('R10',52,'M_SIM_CLK','SIM_CLK'),('R11',55,'M_SIM_RESET','SIM_RESET')]:r(ref,'22R',63,y,a,b,g)
    r('R12','10k',63,58,'MODEM_1V8','SIM_DETECT',g)
    c('C20','100n',68,55,'SIM_VCC','GND',g)
    for i,y,n in [(21,49,'SIM_DATA'),(22,52,'SIM_CLK'),(23,55,'SIM_RESET')]:c(f'C{i}','33p OPTIONAL',68,y,n,'GND',g,dnp=True)
    for ref,x,n in [('D1',71,'SIM_DATA'),('D2',74,'SIM_CLK'),('D3',77,'SIM_RESET'),('D4',80,'SIM_VCC')]:
        add(ref,'SIM ESD <=10pF CANDIDATE','Diode_SMD:D_SOD-323',x,47,{'1':n,'2':'GND'},g,names={'1':['K','passive'],'2':['A','passive']},note='Choose compatible 1.8/3V low-leakage SIM ESD part and verify actual polarity footprint.')
    r('R13','0R RF SERIES',82,13,'RF_ANT','RF_FEED',g)
    c('C24','RF MATCH SHUNT DNP',81,10,'RF_ANT','GND',g,dnp=True)
    c('C25','RF MATCH SHUNT DNP',86,10,'RF_FEED','GND',g,dnp=True)
    add('J11','LTE ANT U.FL','Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical',86,15,{'1':'RF_FEED','2':'GND'},g,note='50 Ohm controlled-impedance route; stack-up and antenna tuning pending.')
    # Population-selected USB route: do not tee the module data pair to two
    # hosts. Place route links at the module with the unused branch isolated.
    # UART remains connected in both population variants.
    hdr('J12','USB SERVICE ONLY - ISOLATED IN HOST BUILD',40,59,['SERVICE_USB_VBUS','SERVICE_USB_DM','SERVICE_USB_DP','GND'],g,90)
    r('R26','0R USB SERVICE DP',79.5,26,'M_USB_DP','SERVICE_USB_DP',g)
    r('R27','0R USB SERVICE DM',79.5,29,'M_USB_DM','SERVICE_USB_DM',g)
    r('R28','0R USB HOST DP DNP',79.5,35,'M_USB_DP','ESP_USB_DP20',g,dnp=True)
    r('R29','0R USB HOST DM DNP',79.5,38,'M_USB_DM','ESP_USB_DM19',g,dnp=True)
    r('R30','0R VBUS FROM SERVICE',83.5,26,'SERVICE_USB_VBUS','USB_DETECT_5V',g)
    r('R31','0R VBUS DETECT FROM SYSTEM DNP',87.5,26,'SYS_5V','USB_DETECT_5V',g,dnp=True)
    g='05 ESP / AUDIO / BUTTON / OPTIONAL RADAR / ADC'
    esp=['ESP_5V','GND','ESP_3V3','GND','ESP_TX17','ESP_RX18','ESP_DTR4','I2S_MIC_BCLK14','I2S_MIC_WS13','I2S_MIC_DATA12','I2S_AMP_BCLK15','I2S_AMP_WS16','I2S_AMP_DATA7','RADAR_TX_TO_IO6','RADAR_RX_FROM_IO8','BOOT_BTN_IO0','ADC_BAT_IO2','ADC_EN_IO9','EXT_PRESENT_N_IO10','PWRKEY_CTL','RESET_CTL','CHRG_OD','DONE_OD','UPS_PG_OD','DEBUG_ESP_TX43','DEBUG_ESP_RX44','ESP_EN','ESP_USB_DM19','ESP_USB_DP20','GND']
    add('J13','ESP32-S3 HARNESS WITH USB19/20 RESERVE','Connector_PinHeader_2.54mm:PinHeader_2x15_P2.54mm_Vertical',33,16,{str(i+1):n for i,n in enumerate(esp)},g,note='Harness draft, not final high-speed connector. Pins28/29 = USB DM19/DP20. PWRKEY GPIO11, RESET GPIO21, ADC GPIO2 proposed; verify dev-board access. Short 90-ohm USB pair/return path required; dev-board native USB cannot simultaneously connect another host.')
    hdr('J14','INMP441 3V3',38,50,['ESP_3V3','GND','I2S_MIC_BCLK14','I2S_MIC_WS13','I2S_MIC_DATA12'],g,90)
    hdr('J15','MAX98357 5V',38,55,['SYS_5V','GND','I2S_AMP_BCLK15','I2S_AMP_WS16','I2S_AMP_DATA7'],g,90)
    hdr('J16','RADAR OPTIONAL TX6 RX8',28,60,['RADAR_5V','GND','RADAR_TX_TO_IO6','RADAR_RX_FROM_IO8'],g,90)
    hdr('JP2','RADAR POWER REMOVE TO OMIT',20,60,['SYS_5V','RADAR_5V'],g,90)
    c('C26','10u 10V',28,55,'RADAR_5V','GND',g,big=True)
    hdr('J17','CALL BUTTON NORMALLY OPEN',53,59,['BOOT_BTN_IO0','GND'],g,90)
    r('R14','10k',52,55,'ESP_3V3','BOOT_BTN_IO0',g)
    c('C27','100n',57,55,'BOOT_BTN_IO0','GND',g)
    hdr('J18','ESP FLASH TTL GND TX43 RX44 5V',43,70,['GND','DEBUG_ESP_TX43','DEBUG_ESP_RX44','TTL_5V'],g,90)
    hdr('JP3','ESP POWER SYS / ESP / TTL',29,70,['SYS_5V','ESP_5V','TTL_5V'],g,90)
    add('SW1','BOOT / CALL','Button_Switch_THT:SW_PUSH_6mm_H5mm',52,65,{'1':'BOOT_BTN_IO0','2':'GND'},g)
    add('SW2','ESP RESET','Button_Switch_THT:SW_PUSH_6mm_H5mm',64,65,{'1':'ESP_EN','2':'GND'},g)
    r('R25','10k',74,69,'ESP_3V3','ESP_EN',g)
    c('C30','100n',79,69,'ESP_EN','GND',g)
    # High-side gated divider prevents a charged battery back-powering a stopped ESP.
    mos('Q3','BSS84',94,18,'BAT_GATE','BAT_SENSE_IN','BAT_DIV_SW',g)
    mos('Q4','2N7002',94,24,'ADC_EN_IO9','GND','BAT_GATE',g)
    r('R15','100k',89,18,'BAT_SENSE_IN','BAT_GATE',g)
    r('R16','100k',89,24,'ADC_EN_IO9','GND',g)
    r('R17','150k 1%',97,29,'BAT_DIV_SW','ADC_BAT_IO2',g)
    r('R18','100k 1%',97,33,'ADC_BAT_IO2','GND',g)
    c('C28','100n',97,37,'ADC_BAT_IO2','GND',g)
    # External input detector is open drain, separate from UPS boosted 5V.
    mos('Q5','2N7002',94,56,'EXT_DETECT_GATE','GND','EXT_PRESENT_N_IO10',g)
    r('R19','100k',94,44,'VIN_EXT_5V','EXT_DETECT_GATE',g)
    r('R20','100k',94,48,'EXT_DETECT_GATE','GND',g)
    r('R21','10k',94,61,'ESP_3V3','EXT_PRESENT_N_IO10',g)
    c('C29','10n',94,52,'EXT_DETECT_GATE','GND',g)
    for ref,x,n in [('R22',10,'CHRG_OD'),('R23',15,'DONE_OD'),('R24',20,'UPS_PG_OD')]:r(ref,'10k DNP UNTIL UPS CONFIRMED',x,48,'ESP_3V3',n,g,dnp=True)
    for ref,x,n in [('TP4',40,'DEBUG_ESP_TX43'),('TP5',44,'DEBUG_ESP_RX44'),('TP6',48,'GND')]:tp(ref,n,x,39,n,g)
    for ref,x,y in [('H1',4,4),('H2',96,4),('H3',4,71),('H4',96,71)]:add(ref,'M3 GENERIC','MountingHole:MountingHole_3.2mm_M3',x,y,{},'MECHANICAL')
    # Placement refinement from actual KiCad courtyard/pad DRC, not body guesses.
    positions={'J1':(14,8),'H1':(3,3),'J2':(8,20),'JP1':(24,13),'C1':(24,8),'C2':(29,8),
      'C10':(66,3),'C11':(63,11),'C12':(66.5,11),
      'J7':(74,41),'J8':(85,43.5),'D1':(70,47),'D2':(74,47),'D3':(78,47),'D4':(82,47),
      'C20':(68,58),'R15':(93,14),'J18':(39,70),'SW2':(62.5,68.5),'J14':(43,52),'J15':(40,57),'J6':(57,48),'J12':(26,65),'J17':(55,60),'R14':(54,56)}
    for fp in board.GetFootprints():
        if fp.GetReference() in positions:fp.SetPosition(v(*positions[fp.GetReference()]))
    for p in parts:
        if p['ref'] in positions:p['x'],p['y']=positions[p['ref']]
    for a,b in [((0,0),(100,0)),((100,0),(100,75)),((100,75),(0,75)),((0,75),(0,0))]:line(board,a,b,pcb.Edge_Cuts,.05)
    # Deliberate reserve drawing, not a made-up solder footprint for unknown PMIC.
    for a,b in [((6,17),(29,17)),((29,17),(29,45)),((29,45),(6,45)),((6,45),(6,17))]:line(board,a,b,pcb.Dwgs_User,.15)
    pcb.SaveBoard(str(ROOT/(PROJECT+'.kicad_pcb')),board)
    data={'revision':'V2-ML307-SMT-UPS-USB-RESERVE','status':'UNROUTED REVIEW DRAFT - NOT FOR FABRICATION','dimensions_mm':[100,75],'parts':parts,'ups_reserved_region_mm':[6,17,23,28],'ups_chip':'User to supply later; no charging/protection/switching design frozen','battery':'Protected 1S 4.2V Li-ion assumed for estimation; chemistry to confirm','adc':{'gpio':2,'channel':'ADC1_CH1','enable_gpio':9,'rtop_ohm':150000,'rbottom_ohm':100000,'cap_farad':1e-7,'scale':2.5,'max_battery_v':4.2,'max_adc_v':1.68},'proposed_gpio':{'external_power_present_n':10,'modem_pwrkey':11,'modem_reset':21,'usb_dm':19,'usb_dp':20},
      'usb_transport_reserve':{'uart_retained':True,'default_population':'service-only AT baseline','service_links':['R26','R27','R30'],'host_links':['R28','R29','R31'],'mutually_exclusive_population':True,'host_firmware_choices':['AT UART','USB RNDIS','USB ECM'],'runtime_switch_implemented':False,'routed':False,'verified_on_hardware':False,'vbus_detect_range_v':[3,5.25],'note':'VBUS detection is not module main power; USB ESD/impedance/final connector/host isolation pending. No two populated data pairs or VBUS sources simultaneously.'},'manufacturing_ready':False,'firmware_modified':False}
    (ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    prior=json.loads((ROOT.parent/'voice_carrier_v1/voice_carrier_v1.kicad_pro').read_text(encoding='utf-8'))
    prior['meta']['filename']=PROJECT+'.kicad_pro'
    (ROOT/(PROJECT+'.kicad_pro')).write_text(json.dumps(prior,indent=2),encoding='utf-8')
    print('Created',len(parts),'parts',len(nets),'nets; UNROUTED')

if __name__=='__main__':ml307_footprint();design()
