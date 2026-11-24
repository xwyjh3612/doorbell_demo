"""Modify the routed V5 baseline in V6 only; native DRC remains authoritative."""
from pathlib import Path
import json, math
import pcbnew as p

ROOT=Path(__file__).resolve().parent
LIB=ROOT.parents[1]/'build/cad-tools/kicad/share/kicad/footprints'
FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
BASE=ROOT.parent/'voice_mainboard_v5'
b=p.LoadBoard(str(BASE/'voice_mainboard_v5.kicad_pcb'))
d=json.loads((BASE/'design.json').read_text(encoding='utf8'))
parts={q['ref']:q for q in d['parts']}
fps={f.GetReference():f for f in b.GetFootprints()}
prices=json.loads((BASE/'cost/part-price-inputs.json').read_text(encoding='utf8'))
held=[]

def xy(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def net(s):
    n=b.FindNet(s)
    if n is None:n=p.NETINFO_ITEM(b,s);b.Add(n)
    return n
def assign(ref,pins):
    parts[ref]['pins']=pins
    for pad in fps[ref].Pads():pad.SetNet(net(pins[pad.GetNumber()])) if pins.get(pad.GetNumber()) else pad.SetNetCode(0)
def remove(ref):
    held.append(fps[ref]);b.Remove(fps.pop(ref));parts.pop(ref);prices.pop(ref,None)
def load(fpname):
    lib,name=fpname.split(':')
    return p.FootprintLoad(str(ROOT/'VoiceV2.pretty' if lib=='VoiceV2' else LIB/(lib+'.pretty')),name)
def add(ref,value,fpname,x,y,pins,names=None,angle=0,cny=None,source='',note='',dnp=False,group='02 INTEGRATED UPS / POWER STATUS'):
    assert ref not in parts and ref not in fps, 'Duplicate reference '+ref
    f=load(fpname);f.SetReference(ref);f.SetValue(value);f.SetPosition(xy(x,y));f.SetOrientationDegrees(angle)
    f.SetDNP(dnp);f.Value().SetVisible(False);f.Reference().SetVisible(False);b.Add(f);fps[ref]=f
    parts[ref]={'ref':ref,'value':value,'mpn':value,'lcsc':None,'footprint':fpname,'pins':pins,'names':names or {},'x':x,'y':y,'angle':angle,'group':group,'dnp':dnp,'source':source,'note':note,'kind':'pcb','side':'F','price_basis':'public tier if cited; other passives unquoted'}
    prices[ref]={'unit_cny':cny,'basis':'public1000 tier' if cny is not None and source else 'not quoted','source':source}
    assign(ref,pins);return f
def custom(name,geometry,description,th=False):
    f=p.FOOTPRINT(None);f.SetFPID(p.LIB_ID('VoiceV2',name));f.SetLibDescription(description)
    f.SetAttributes(p.FP_THROUGH_HOLE if th else p.FP_SMD)
    for number,x,y,w,h in geometry:
        pd=p.PAD(f);pd.SetNumber(str(number));pd.SetPosition(xy(x,y));pd.SetSize(xy(w,h))
        pd.SetShape(p.PAD_SHAPE_ROUNDRECT);pd.SetRoundRectRadiusRatio(.1)
        pd.SetAttribute(p.PAD_ATTRIB_SMD);ls=p.LSET()
        for la in [p.F_Cu,p.F_Mask,p.F_Paste]:ls.AddLayer(la)
        pd.SetLayerSet(ls);f.Add(pd)
    xs=[x-w/2 for _,x,y,w,h in geometry]+[x+w/2 for _,x,y,w,h in geometry]
    ys=[y-h/2 for _,x,y,w,h in geometry]+[y+h/2 for _,x,y,w,h in geometry]
    for la,pad in [(p.F_CrtYd,.25),(p.F_Fab,0)]:
        xmin,xmax,ymin,ymax=min(xs)-pad,max(xs)+pad,min(ys)-pad,max(ys)+pad
        pts=[(xmin,ymin),(xmax,ymin),(xmax,ymax),(xmin,ymax)]
        for a,z in zip(pts,pts[1:]+pts[:1]):
            sh=p.PCB_SHAPE(f);sh.SetShape(p.SHAPE_T_SEGMENT);sh.SetStart(xy(*a));sh.SetEnd(xy(*z));sh.SetLayer(la);sh.SetWidth(p.FromMM(.05));f.Add(sh)
    p.FootprintSave(str(ROOT/'VoiceV2.pretty'),f)

# Preserve every pre-existing circuit before allocating UPS references.
for oldref,newref in [('L4','L5'),('R61','R75'),('R62','R76'),('TP12','TP15'),('TP13','TP16'),('TP14','TP17')]:
    assert newref not in parts
    q=parts.pop(oldref);q['ref']=newref;parts[newref]=q
    f=fps.pop(oldref);f.SetReference(newref);fps[newref]=f
    if oldref in prices:prices[newref]=prices.pop(oldref)

# Remove only copper that terminates at the old interface / replaced modem loop.
changed_nets={'BUCK_SW','BUCK_FB','BUCK_EN','BUCK_BST'}
old=fps['U15'];oldpads=[pd.GetPosition() for pd in old.Pads()]
for t in list(b.GetTracks()):
    near_old=any(math.dist((p.ToMM(pt.x),p.ToMM(pt.y)),(p.ToMM(z.x),p.ToMM(z.y)))<1.4 for pt in [t.GetStart(),t.GetEnd()] for z in oldpads)
    if t.GetNetname() in changed_nets or near_old:held.append(t);b.Remove(t)
for z in list(b.Zones()):
    box=z.GetBoundingBox()
    old_contract=z.GetIsRuleArea() and abs(p.ToMM(box.GetX())-14)<.01 and abs(p.ToMM(box.GetY())-55)<.01
    if not z.GetIsRuleArea() or old_contract:held.append(z);b.Remove(z)
remove('U15');remove('U2');remove('R1');remove('C3')
# The modem regulator now shares the 2.5-5.5V SY8089A1 family with ESP.
add('U2','SY8089A1AAC','Package_TO_SOT_SMD:SOT-23-5',50,11,{'1':'SYS_5V','2':'GND','3':'BUCK_SW','4':'SYS_5V','5':'BUCK_FB'},
    names={'1':['EN','input'],'2':['GND','power_in'],'3':['LX','passive'],'4':['IN','power_in'],'5':['FB','input']},cny=.29263,
    source='https://file.huaqiu.com/web1/M00/97/C7/o4YBAF0Rz_6AEbagAAxEzJRIyYA704.pdf',group='01 EXTERNAL INPUT / MODEM BUCK',note='2.5-5.5V input,2A class. 100k/18.7k gives3.80856V. Current vendor revision and transient qualification pending.')
for ref,value in [('R2','100k 0.1% MODEM RH'),('R3','18.7k 0.1% MODEM RL'),('C37','22p MODEM CFF')]:
    parts[ref]['value']=parts[ref]['mpn']=value;fps[ref].SetValue(value)
parts['Q6']['note']='Adapter reverse polarity only; downstream TPS2117 prevents backfeed. SOT23 G1/S2/D3.'

# ETA1096 manufacturer recommended land, page8, including analog thermal pad9.
geo=[(i,-2.85,-1.905+(i-1)*1.27,1.6,.8) for i in range(1,5)]
geo += [(i,2.85,1.905-(i-5)*1.27,1.6,.8) for i in range(5,9)]+[(9,0,0,2.8,3.6)]
custom('ETA1096_ESOP8',geo,'ETA1096 datasheet page8 recommended land: pad span7.3,1.6x0.8,pitch1.27,EP2.8x3.6. EP9=AGND.')
# CPC5 top-view pads transcribed from the archived exact AJL manufacturer drawing.
custom('XB7608_CPC5',[(1,-.795,1.75,.30,1.1),(2,-.265,1.75,.30,1.1),(3,.795,1.75,.30,1.1),(4,.53,-1.75,.85,1.1),(5,-.53,-1.75,.85,1.1)],
       'AJL datasheet pages2/11: pin1 lower-left; pin2+3 lowerCELL_NEG,4+5 upperVM. Body2.5-2.7,lead span3.85-4.15,pitch0.53/1.06. Land derived from outline; assembler review pending.')

add('U15','ETA1096E8A','VoiceV2:ETA1096_ESOP8',32,64,
    {'1':'GND','2':'BOOST_EN','3':'UPS_SW','4':'BAT_SENSE_IN','5':'UPS_FB','6':'UPS_ISET','7':'BAT_BOOST_5V','8':'GND','9':'GND'},
    names={'1':['GP','power_in'],'2':['EN','input'],'3':['SW','passive'],'4':['IN','power_in'],'5':['FB','input'],'6':['ISET','passive'],'7':['OUT','power_out'],'8':['GP','power_in'],'9':['AGND_EP','power_in']},cny=1.2694,source='https://item.szlcsc.com/8449074.html',note='Battery branch only, boost standby enabled for quick transfer. New circuit, not XR2981 pin-compatible.')
add('L4','SWPA6045S2R2MT','Inductor_SMD:L_Sunlord_SWPA6045S',24,62,{'1':'BAT_SENSE_IN','2':'UPS_SW'},cny=.2756,source='https://item.szlcsc.com/84619.html',note='2.2uH, Isat6.75A/Irms4.6A catalog; stock21 requires alternate/lead-time before1000pcs.')
add('U16','TP4056-MS','Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm',43,55,
    {'1':'BAT_TEMP','2':'CHG_PROG','3':'GND','4':'VIN_PROTECTED','5':'BAT_SENSE_IN','6':'CHG_FULL_N','7':'CHG_ACTIVE_N','8':'CHG_CE','9':'GND'},
    names={str(i):[n,t] for i,n,t in [(1,'TEMP','input'),(2,'PROG','passive'),(3,'GND','power_in'),(4,'VCC','power_in'),(5,'BAT','power_out'),(6,'STDBY','open_collector'),(7,'CHRG','open_collector'),(8,'CE','input'),(9,'EP','passive')]},cny=.1626,source='https://item.szlcsc.com/8533532.html',note='Replaces FY4056T in a new circuit; pin8 CE, EP grounded. Rprog4k=300mA; disable during calls.')
add('U17','XB7608AJL','VoiceV2:XB7608_CPC5',17,63,
    {'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NEG','4':'GND','5':'GND'},
    names={'1':['VDD','power_in'],'2':['CELL_GND','passive'],'3':['CELL_GND','passive'],'4':['PACK_NEG','passive'],'5':['PACK_NEG','passive']},cny=.2875,source='https://item.szlcsc.com/3400478.html',note='One integrated protection, not two FM5608 in guessed parallel.6A min overcurrent@3.6V;3.0V supervisor cuts boost earlier. Exact land review pending.')
add('U18','TPS2117DRLR','VoiceV2:TI_DRL0008A',53,63,
    {'1':'GND','2':'SYS_5V','3':'VIN_PROTECTED','4':'UPS_PR1','5':'VIN_PROTECTED','6':'BAT_BOOST_5V','7':'SYS_5V','8':'SUPPLY_BAT_N47'},
    names={'1':['GND','power_in'],'2':['VOUT','power_out'],'3':['VIN1','power_in'],'4':['PR1','input'],'5':['MODE','input'],'6':['VIN2','power_in'],'7':['VOUT_COMMON','passive'],'8':['ST','open_collector']},cny=1.91,source='https://item.szlcsc.com/24017237.html',note='Pins2/7 internally common output represented by one ERC driver. Priority external.4A switch selected for controlled startup of existing470u reservoir and low drop; product output requirement2A unchanged.')
add('U19','ME2807A30M3G','Package_TO_SOT_SMD:SOT-23',24,55,{'1':'BOOST_EN','2':'GND','3':'BAT_SENSE_IN'},names={'1':['RESET_N','output'],'2':['GND','power_in'],'3':['VIN','power_in']},cny=.251,source='https://item.szlcsc.com/236196.html',note='3.0V falling cutoff ±1%, hysteresis2-10%; CMOS output to boost EN, no ESP5V exposure.')
add('J23','1S CELL + / - / NTC','Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical',11,64,{'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NTC'},note='Bare1S battery negative must NOT connectGND; return goes through U17. NTC10kB3950 referencedCELL_NEG. No input5V here.')

def r(ref,value,x,y,a,z,**kw):return add(ref,value,'Resistor_SMD:R_0603_1608Metric',x,y,{'1':a,'2':z},**kw)
def c(ref,value,x,y,a,z,fp='Capacitor_SMD:C_0805_2012Metric',**kw):return add(ref,value,fp,x,y,{'1':a,'2':z},**kw)
c('C64','22u 10V X5R',26,67,'BAT_SENSE_IN','GND')
c('C65','22u 10V X5R',38,62,'BAT_BOOST_5V','GND')
c('C66','22u 10V X5R',32,70,'BAT_BOOST_5V','GND')
c('C67','10u 10V X5R',43,49,'VIN_PROTECTED','GND')
c('C68','10u 10V X5R',43,61,'BAT_SENSE_IN','GND')
c('C69','100n',17,59,'BAT_SENSE_IN','CELL_NEG',fp='Capacitor_SMD:C_0603_1608Metric')
c('C70','100n',24,52,'BAT_SENSE_IN','GND',fp='Capacitor_SMD:C_0603_1608Metric')
c('C71','22u 10V X5R',49,59,'VIN_PROTECTED','GND')
c('C72','22u 10V X5R',49,68,'SYS_5V','GND')
c('C73','22u 10V X5R',57,67,'BAT_BOOST_5V','GND')
r('R61','73.2k 0.1%',39,67,'BAT_BOOST_5V','UPS_FB')
r('R62','10k 0.1%',39,70,'UPS_FB','GND')
r('R63','30k 1% ISET',38.4,64.3,'UPS_ISET','GND',note='6A typical limit; minimum not specified; qualify low-battery2A peak before release.')
r('R64','4k 1% 300mA',37.3,55,'CHG_PROG','GND')
r('R65','6.19k 1% NTC TOP',37,49,'VIN_PROTECTED','BAT_TEMP')
r('R66','49.9k 1% NTC BOTTOM',36,52,'BAT_TEMP','GND')
r('R67','0R NTC LINK',20,55,'CELL_NTC','BAT_TEMP')
r('R68','10k',49,55,'VIN_PROTECTED','CHG_CE')
add('Q7','2N7002K-7','Package_TO_SOT_SMD:SOT-23',48,49,{'1':'CHG_DISABLE_IO38','2':'GND','3':'CHG_CE'},names={'1':['G','input'],'2':['S','passive'],'3':['D','passive']},cny=.0958,source='https://item.szlcsc.com/85561.html',note='ESP38 high pauses charging during ringing/call; gate pull-down default charging enabled.')
r('R69','100k',54,52,'CHG_DISABLE_IO38','GND')
r('R70','100k 0.1% PR TOP',57,60,'VIN_PROTECTED','UPS_PR1')
r('R71','33.2k 0.1% PR BOTTOM',57,63,'UPS_PR1','GND',note='Nominal transfer4.012V; TI reference + resistor corners3.687-4.340V. Chosen to ensure5V adapter priority despite ±8% mux reference. Transfer/dropout measurement required.')
r('R72','10k',60,62,'ESP_3V3','SUPPLY_BAT_N47')
r('R73','10k',38,45,'ESP_3V3','CHG_ACTIVE_N')
r('R74','10k',43,45,'ESP_3V3','CHG_FULL_N')
add('TP12','MUX ST / GPIO47','TestPoint:TestPoint_Pad_D1.0mm',61,65,{'1':'SUPPLY_BAT_N47'})
add('TP13','BAT BOOST 5V','TestPoint:TestPoint_Pad_D1.0mm',38,72,{'1':'BAT_BOOST_5V'})
add('TP14','CELL NEG isolated','TestPoint:TestPoint_Pad_D1.0mm',16,55,{'1':'CELL_NEG'})
for number,s,name in [('24','SUPPLY_BAT_N47','IO47'),('34','CHG_DISABLE_IO38','IO38'),('25','CHG_ACTIVE_N','IO48'),('39','CHG_FULL_N','IO1')]:
    pins=dict(parts['U7']['pins']);pins[number]=s;assign('U7',pins);parts['U7']['names'][number]=[name,'bidirectional']
for ref,code in [('U15','C7435200'),('U16','C7473158'),('U17','C2980178'),('U18','C22399676'),('U19','C236756')]:parts[ref]['lcsc']=code
parts['L4']['lcsc']='C83455'
for z in b.GetDrawings():
    if isinstance(z,p.PCB_TEXT) and ('UPS' in z.GetText() or 'V5' in z.GetText()):
        z.SetText(z.GetText().replace('V5','V6').replace('UPS REG5V IC TBD','UPS INTEGRATED').replace('UPS5V CONTRACT','ETA1096 UPS'))
d.update(revision='V6-INTEGRATED-UPS-20261124',status='IN PROGRESS / NATIVE UPS CIRCUIT / UNRELEASED',parts=list(parts.values()),parent_PCB_sha256='86ffef9a4483c9eaaddd3a9944b9e787a9cc851e0d3be6589e4c84f68b37c903')
d['gpio_contract'].update(actual_supply_battery_n=47,charger_disable=38,charging_active_n=48,charging_full_n=1)
d['ups_controls']={'actual_chip_selected':True,'boost':'ETA1096E8A','charger':'TP4056-MS','protection':'XB7608AJL','mux':'TPS2117DRLR','boost_low_voltage_supervisor':'ME2807A30M3G','full_UPS_qualified':False,'output_is_user_assumption':False,'output_nominal_v':5,'peak_output_a':2,'continuous_current_a':None,'actual_source_ST_gpio':47,'external_presence_gpio':10,'battery_ADC_gpio':2,'ADC_switch_gpio':9,'cell_connection':['BAT_SENSE_IN','CELL_NEG','CELL_NTC'],'unprotected_negative_is_board_ground':False,'charge_current_ma':300,'charging_paused_during_calls':True}
d['assembly_open_items']=[x for x in d['assembly_open_items'] if not x.startswith('Actual UPS')]+['Exact protection and charger land patterns, supplier footprint review','ETA1096 limit minimum at30k, low-battery peak and mux startup/transfer measurement','Selected battery NTC and charge/temperature limits; external input2A peak plus charge pause firmware']
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'cost/part-price-inputs.json').write_text(json.dumps(prices,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
b.BuildConnectivity();p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
print('V6 integrated UPS footprints and net contracts saved',len(parts),'parts')
