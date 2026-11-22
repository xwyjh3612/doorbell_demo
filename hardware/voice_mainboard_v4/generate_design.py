"""V4 cost-oriented two-layer integrated ESP/4G/amplifier board.

Native CAD engineering candidate, not production signoff. Run once to create
placement; rerunning removes routing. V3 is read-only and remains recoverable.
"""
from pathlib import Path
import importlib.util, json, shutil, math
import pcbnew as p

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'voice_mainboard_v3'
PROJECT='voice_mainboard_v4'
LOCAL=ROOT/'VoiceV2.pretty';LOCAL.mkdir(parents=True,exist_ok=True)
(ROOT/'exports').mkdir(exist_ok=True);(ROOT/'cost').mkdir(exist_ok=True)
for f in (BASE/'VoiceV2.pretty').glob('*.kicad_mod'):shutil.copy2(f,LOCAL/f.name)
spec=importlib.util.spec_from_file_location('v2helper',BASE.parent/'voice_mainboard_v2/generate_design.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
g.ROOT=ROOT;g.LOCAL=LOCAL;g.PROJECT=PROJECT;g.board=p.BOARD();g.board.SetCopperLayerCount(2)
g.parts=[];g.nets={};board=g.board
data=json.loads((BASE/'design.json').read_text(encoding='utf8'))
old={x['ref']:x for x in data['parts']}
prices={}

def add(ref,value,footprint,x,y,pins,group,angle=0,names=None,dnp=False,source='',note='',mpn=None,lcsc=None,price=None,basis='unquoted procurement target'):
    f=g.add(ref,value,footprint,x,y,pins,group,angle,names,dnp,source,note)
    f.SetAttributes(p.FP_THROUGH_HOLE if any(pd.GetAttribute()==p.PAD_ATTRIB_PTH for pd in f.Pads())else p.FP_SMD)
    part=g.parts[-1];part.update(mpn=mpn or value,lcsc=lcsc,side='F',price_basis=basis)
    if price is not None:prices[ref]={'unit_cny':price,'basis':basis,'source':source}
    return f
def copy(ref,x,y,group=None,remap=None,price=None,mpn=None,basis=None):
    q=old[ref];pins={k:(remap or {}).get(v,v)for k,v in q['pins'].items()}
    return add(ref,q['value']if mpn is None else mpn,q['footprint'],x,y,pins,group or q['group'],q.get('angle',0),q['names'],q['dnp'],q.get('source',''),q.get('note',''),mpn or q.get('mpn'),q.get('lcsc'),price,basis or 'unquoted procurement target')
def r(ref,value,x,y,a,b,group,angle=0,dnp=False,precision=False):
    return add(ref,value,'Resistor_SMD:R_0603_1608Metric',x,y,{'1':a,'2':b},group,angle,dnp=dnp,price=.06 if precision else .025)
def c(ref,value,x,y,a,b,group,angle=0,dnp=False,big=False):
    return add(ref,value,'Capacitor_SMD:C_0805_2012Metric'if big else'Capacitor_SMD:C_0603_1608Metric',x,y,{'1':a,'2':b},group,angle,dnp=dnp,price=.2619 if big else .05,basis='V3 page reference, tier unconfirmed'if big else'unquoted passive allowance')
def hdr(ref,value,x,y,signals,group,angle=0,dnp=False,price=.15):
    return add(ref,value,f'Connector_PinHeader_2.54mm:PinHeader_1x{len(signals):02d}_P2.54mm_Vertical',x,y,{str(i+1):n for i,n in enumerate(signals)},group,angle,dnp=dnp,price=price)
def mos(ref,value,x,y,gate,source,drain,group,price=.2474,mpn='2N7002K-7'):
    return add(ref,value,'Package_TO_SOT_SMD:SOT-23',x,y,{'1':gate,'2':source,'3':drain},group,names={'1':['G','input'],'2':['S','passive'],'3':['D','passive']},mpn=mpn,price=price)
def tp(ref,value,x,y,net,group):
    return add(ref,value,'TestPoint:TestPoint_Pad_D1.0mm',x,y,{'1':net},group,price=0,basis='copper test pad, no purchased component')
def button(ref,x,y,net,group):
    return add(ref,'TACT 4.5x4.5 SMD','Button_Switch_SMD:SW_SPST_TL3342',x,y,{'1':net,'2':'GND'},group,price=.18)

# External 5V input and a single 3.792V 3A-rated primary buck. No expensive
# upstream regulated-5V stage is placed in series with the modem.
A='01 EXTERNAL INPUT / PRIMARY 3.8V'
copy('J1',.5,46,A,price=.3837,basis='V3 page reference, quantity tier unconfirmed')
copy('F1',18,43,A,price=.4972,basis='V3 page reference, quantity tier unconfirmed')
copy('Q6',22,43,A,price=.3881,basis='V3 page reference, quantity tier unconfirmed')
r('R32','100k',22,47,'REVERSE_GATE','GND',A)
copy('U2',28,47,A,{'POWER_BUS':'VIN_PROTECTED','BUCK_3V8':'ADAPTER_3V8'},2.65,basis='V3 page reference, quantity tier unconfirmed')
r('R1','100k',25,43,'VIN_PROTECTED','BUCK_EN',A)
c('C3','100n BST',28,43,'BUCK_BST','BUCK_SW',A)
c('C4','22u 16V',24,50,'VIN_PROTECTED','GND',A,big=True)
c('C5','22u 16V',20,50,'VIN_PROTECTED','GND',A,big=True)
copy('L1',33,47,A,{'BUCK_3V8':'ADAPTER_3V8'},.2756,basis='V3 selected inductor page reference')
c('C6','22u 16V',33,52,'ADAPTER_3V8','GND',A,big=True)
c('C7','22u 16V',37,52,'ADAPTER_3V8','GND',A,big=True)
r('R2','37.4k 0.1%',28,53,'ADAPTER_3V8','BUCK_FB',A,precision=True)
r('R3','10k 0.1%',28,56,'BUCK_FB','GND',A,90,precision=True)
c('C37','33p CFF',31,56,'ADAPTER_3V8','BUCK_FB',A)

# Battery path is selected before modem/ESP/5V conversion. The protected pack
# remains an external purchased assembly. Analog cutoff does not depend on MCU.
B='02 CHARGE / BATTERY / UV / POWER MUX'
hdr('J2','PROTECTED 1S BATTERY + GND',8,65,['BAT_SENSE_IN','GND'],B,90,price=.35)
hdr('J4','PACK NTC 10k B3950',11,71,['NTC_PACK','GND'],B,90)
copy('U8',17,64,B,price=.12,mpn='TP4056 ESOP8',basis='unquoted procurement target; exact manufacturer/stencil approval pending')
c('C38','10u',12,59,'VIN_PROTECTED','GND',B,big=True)
c('C39','10u',12,63,'BAT_SENSE_IN','GND',B,big=True)
r('R35','12k 100mA',18,69,'UPS_CHG_PROG','GND',B)
r('R36','9.1k 1%',20,59,'VIN_PROTECTED','UPS_TEMP',B)
mos('Q8','2N7002K CE DISABLE',24,64,'CHG_DISABLE_IO38','GND','UPS_CHG_CE',B)
r('R39','100k',24,68,'CHG_DISABLE_IO38','GND',B)
# Original V3 TP4056 manufacturer-ratio NTC circuit, no generic BMS guess.
for ref,(x,y)in {'R37':(12,68),'R38':(12,72)}.items():
    copy(ref,x,y,B,price=.05 if ref.startswith('C')else .025)

copy('D5',35,63,B,price=.0431,basis='V3 BAT54C page reference; two anodes VIN/BAT to AUX')
copy('U12',39,64,B,price=1.25,basis='V3 TLV431B page reference')
r('R42','3.3k',39,59,'UPS_CTL_VCC','UPS_REF_1V24',B)
r('R43','10k 0.1%',43,61,'UPS_REF_1V24','UPS_REF_0V62',B,precision=True)
r('R44','10k 0.1%',43,65,'UPS_REF_0V62','GND',B,precision=True)
c('C49','100n',39,68,'UPS_REF_1V24','GND',B)
add('U11','LM393LVDGKR','Package_SO:VSSOP-8_3x3mm_P0.65mm',49,65,
 {'1':'BAT_UV_GOOD','2':'UPS_REF_0V62','3':'UPS_BAT_UV_SENSE','4':'GND','5':'UPS_EXT_SENSE','6':'UPS_REF_0V62','7':'UPS_EXT_VALID','8':'UPS_CTL_VCC'},B,
 names={'1':['OUTA','open_collector'],'2':['INA-','input'],'3':['INA+','input'],'4':['GND','power_in'],'5':['INB+','input'],'6':['INB-','input'],'7':['OUTB','open_collector'],'8':['VCC','power_in']},price=1.0033,basis='V3 page reference')
c('C50','100n',49,61,'UPS_CTL_VCC','GND',B)
r('R45','100k 0.1%',53,69,'BAT_SENSE_IN','UPS_BAT_UV_SENSE',B,precision=True)
r('R46','19.6k 0.1%',57,69,'UPS_BAT_UV_SENSE','GND',B,precision=True)
r('R47','2.2M 1% hysteresis',57,72,'BAT_UV_GOOD','UPS_BAT_UV_SENSE',B)
r('R48','10k',49,72,'UPS_CTL_VCC','BAT_UV_GOOD',B)
c('C51','10n',53,72,'UPS_BAT_UV_SENSE','GND',B)
mos('Q9','2N7002K BAT GATE',34,69,'BAT_UV_GOOD','GND','BAT_POWER_GATE',B)
r('R55','100k',30,69,'BAT_SENSE_IN','BAT_POWER_GATE',B)
mos('Q10','DMP2035U BAT ISOLATE',34,58,'BAT_POWER_GATE','BAT_SENSE_IN','BAT_ALLOWED',B,.3881,'DMP2035U-7')
r('R50','100k 1%',54,59,'VIN_PROTECTED','UPS_EXT_SENSE',B)
r('R51','18.2k 1%',58,59,'UPS_EXT_SENSE','GND',B)
r('R52','10M 1% hysteresis',58,62,'UPS_EXT_VALID','UPS_EXT_SENSE',B)
r('R53','10k',54,62,'UPS_CTL_VCC','UPS_EXT_VALID',B)
c('C52','10n',58,65,'UPS_EXT_SENSE','GND',B)
# Buck PG is open drain, wired with external-valid comparator. Do not select
# VIN1 during primary regulator startup merely because the adapter is present.
r('R34','0R PG QUALIFY',40,53,'MODEM_REG_PG','UPS_EXT_VALID',B)
add('U10','TPS2117DRLR','VoiceV2:TI_DRL0008A',44,48,
 {'1':'GND','2':'POWER_BUS','3':'ADAPTER_3V8','4':'UPS_EXT_VALID','5':'UPS_CTL_VCC','6':'BAT_ALLOWED','7':'POWER_BUS','8':'POWER_SOURCE_ST'},B,
 names=old['U10']['names'],source='https://www.ti.com/lit/ds/symlink/tps2117.pdf',price=1.91,basis='V3 page reference')
c('C53','22u 16V',40,46,'ADAPTER_3V8','GND',B,big=True)
c('C54','22u 16V',40,50,'BAT_ALLOWED','GND',B,big=True)
c('C55','22u 16V',48,47,'POWER_BUS','GND',B,big=True)
r('R56','10k STATUS',48,52,'ESP_3V3','POWER_SOURCE_ST',B)

C='03 MODEM / UART / RESET'
modem=json.loads((ROOT/'sources/ml307c-dl-library.json').read_text(encoding='utf8'))
assert modem['model']=='ML307C-DL' and len(modem['pin_names'])==109
q=old['U1'];modem_pins={k:'POWER_BUS' if v=='MODEM_3V8' else v for k,v in q['pins'].items()}
modem_names={k:[name,'no_connect' if name=='RSV' else 'power_in' if name in ['GND','VBAT','USB_VBUS'] else
                  'power_out' if name in ['VDD_EXT','USIM0_PWR','USIM1_PWR'] else
                  q['names'][k][1] if q['names'][k][1]!='no_connect' else 'bidirectional']
             for k,name in modem['pin_names'].items()}
add('U1','ML307C-DL','VoiceV2:ML307C_DL_109_LIBRARY_REVIEW',66,26,modem_pins,C,names=modem_names,
    source=modem['source_url'],mpn='ML307C-DL',lcsc='C48972417',price=10,
    basis='user specified 10 CNY procurement target; no order quote',
    note='C-DL-specific JLCEDA/EasyEDA Official Library symbol and pads. https://lceda.cn/ https://easyeda.com . '
         'SIM0 used; SIM1/GPIO changes left unconnected. HW manual, AT/USB firmware and stencil approval pending.')
add('C8','OCV471M1ATR-1010 470u 10V','Capacitor_SMD:CP_Elec_10x10.5',65,8,{'1':'POWER_BUS','2':'GND'},C,mpn='OCV471M1ATR-1010',lcsc='C250035',price=1.1262,basis='V3 public page reference; land/loop validation pending',note='470uF replaces two 220uF candidates by capacitance only; physical and converter dynamic validation still required.')
c('C10','10u 10V',57,8,'POWER_BUS','GND',C,big=True)
c('C11','100n',61,14,'POWER_BUS','GND',C)
c('C12','33p',66,14,'POWER_BUS','GND',C)
for ref,y,a,b,direction in [('U3',19,'ESP_TX17','M_RX_1V8','ESP_3V3'),('U4',25,'ESP_RX18','M_TX_1V8','GND'),('U5',31,'ESP_DTR4','M_DTR_1V8','ESP_3V3')]:
    add(ref,'SN74LVC1T45DBVR','Package_TO_SOT_SMD:SOT-23-6',46,y,{'1':'ESP_3V3','2':'GND','3':a,'4':b,'5':direction,'6':'MODEM_1V8'},C,names=old[ref]['names'],source='https://www.ti.com/lit/ds/symlink/sn74lvc1t45.pdf',price=.40,note='1.65-5.5V rails; fixed UART direction, power-off isolation. Verify 921600 baud and rail sequencing on prototype.')
for i,y in enumerate([19,25,31]):
    c(f'C{13+i*2}','100n',41,y,'ESP_3V3','GND',C)
    c(f'C{14+i*2}','100n',51,y,'MODEM_1V8','GND',C)
r('R4','10k',41,35,'ESP_3V3','ESP_TX17',C)
r('R5','100k',46,35,'ESP_DTR4','GND',C)
copy('Q1',52,43,C,price=.2474);copy('R6',47,43,C,price=.025)
copy('Q2',65,43,C,price=.2474);copy('R8',70,43,C,price=.025);copy('C19',65,39.5,C,price=.05)
button('SW3',56,41,'MODEM_PWRKEY_N',C)
r('R7','4.7k AUTO ON DNP',59,43,'MODEM_PWRKEY_N','GND',C,dnp=True)
hdr('J8','MODEM DOWNLOAD STRAP OPEN NORMAL',78,43,['MODEM_BOOT_N','GND'],C,90,dnp=True)
for ref,(x,y,n)in {'TP2':(82,24,'MODEM_STATE_1V8'),'TP3':(82,27,'MODEM_NETLIGHT'),'TP12':(83,37,'DBG_TX_1V8'),'TP13':(87,37,'DBG_RX_1V8'),'TP14':(91,37,'MODEM_1V8')}.items():tp(ref,n,x,y,n,C)

D='04 SIM / RF / OPTIONAL USB'
copy('J10',77,55,D,price=2.51,basis='V3 JAE SIM socket page reference; lower-cost replacement not yet qualified')
for ref,y in [('R9',49),('R10',52),('R11',55)]:copy(ref,63,y,D,price=.025)
copy('R12',63,58,D,price=.025);copy('C20',68,58,D,price=.05)
for ref,x in [('D1',71),('D2',75),('D3',79),('D4',83)]:copy(ref,x,47,D,price=.8525,basis='V3 low-capacitance SIM ESD reference; retained until array qualifies')
copy('R13',81,19.4,D,price=.025);copy('C24',78.5,18.625,D,price=.05);copy('C25',83.65,18.625,D,price=.05)
copy('J11',83,23.5,D,price=.30)
hdr('J12','MODEM USB SERVICE VBUS DM DP GND',94,28,['SERVICE_USB_VBUS','SERVICE_USB_DM','SERVICE_USB_DP','GND'],D,dnp=True)
for ref in ['R26','R27','R28','R29','R30','R31']:
    q=old[ref];copy(ref,q['x'],q['y'],D,price=.025)
hdr('J22','USB HOST RESERVE GND DP20 DM19',87,43,['GND','ESP_USB_DP20','ESP_USB_DM19'],D,dnp=True)

E='05 ESP32-S3 / BOOT / TTL / RADAR'
esp_pins={str(n):''for n in range(1,42)}
esp_pins.update({'1':'GND','2':'ESP_3V3','3':'ESP_EN','4':'ESP_DTR4','6':'RADAR_RX6','7':'I2S_SPK_DATA7','8':'I2S_SPK_BCLK15','9':'I2S_SPK_WS16','10':'ESP_TX17','11':'ESP_RX18','12':'RADAR_TX8','13':'ESP_USB_DM19','14':'ESP_USB_DP20','17':'BAT_ADC_EN9','18':'EXT_PRESENT_N_IO10','19':'PWRKEY_CTL','20':'I2S_MIC_DATA12','21':'I2S_MIC_WS13','22':'I2S_MIC_BCLK14','23':'RESET_CTL','27':'CALL_BOOT0','31':'CHG_DISABLE_IO38','36':'DEBUG_ESP_RX44','37':'DEBUG_ESP_TX43','38':'BAT_ADC2','40':'GND','41':'GND'})
esp_names={str(n):[('GND'if n in [1,40,41]else'3V3'if n==2 else'EN'if n==3 else f'PAD{n}'),('power_in'if n in [1,2,40,41]else'input'if n==3 else'no_connect'if n in [28,29,30]else'bidirectional')]for n in range(1,42)}
esp=add('U7','ESP32-S3-WROOM-1-N8R8','RF_Module:ESP32-S3-WROOM-1',20,13,esp_pins,E,names=esp_names,source='https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf',price=12,basis='user specified 12 CNY material cost; N8R8 supplier price unconfirmed',note='8MB flash/8MB octal PSRAM; IO35/36/37 unavailable. Antenna keepout in standard KiCad footprint. Firmware PSRAM 120MHz configuration requires hardware revision validation. EP plated drills changed to0.3mm/0.7mm pads for conventional drilling; assembly tenting/paste review pending.')
esp.SetAttributes(p.FP_SMD)
for pd in esp.Pads():
    if pd.GetAttribute()==p.PAD_ATTRIB_PTH:
        assert pd.GetNumber()=='41'
        pd.SetDrillSize(p.VECTOR2I(p.FromMM(.3),p.FromMM(.3)))
        pd.SetSize(p.VECTOR2I(p.FromMM(.7),p.FromMM(.7)))
r('R57','10k EN',35,8,'ESP_3V3','ESP_EN',E)
c('C56','1u EN delay',35,12,'ESP_EN','GND',E)
c('C57','22u',35,17,'ESP_3V3','GND',E,big=True)
c('C58','100n',35,21,'ESP_3V3','GND',E)
button('SW1',18,33,'CALL_BOOT0',E);r('R14','10k BOOT',24,33,'ESP_3V3','CALL_BOOT0',E)
button('SW2',22,41,'ESP_EN',E)
hdr('J18','TTL GND TX43 RX44 5V',35,38,['GND','DEBUG_ESP_TX43','DEBUG_ESP_RX44','VIN_DC'],E,90)
hdr('J17','EXTERNAL CALL BUTTON',8,38,['CALL_BOOT0','GND'],E,90)
hdr('J16','OPTIONAL RADAR 5V GND RX6 TX8',88,63,['RADAR_5V','GND','RADAR_RX6','RADAR_TX8'],E)
r('R58','0R RADAR POWER OPTIONAL',89,58,'SYS_5V','RADAR_5V',E,dnp=True)
# ADC gate is the audited V3 150k/100k network, adapted to direct MCU module.
for ref,(x,y)in {'Q3':(6,30),'Q4':(11,29),'R15':(6,23),'R16':(11,23),'R17':(6,26),'R18':(11,26),'C28':(16,28)}.items():
    q=old[ref];copy(ref,x,y,E,{'ADC_EN_IO9':'BAT_ADC_EN9','ADC_BAT_IO2':'BAT_ADC2'},.335 if ref=='Q3'else .2474 if ref=='Q4'else .05 if ref.startswith('C')else .025)
copy('Q5',5,56,E,price=.2474)
copy('R19',5,49,E,price=.025);copy('R20',5,52,E,price=.025);copy('R21',5,60,E,price=.025);copy('C29',9,56,E,price=.05)

F='06 ESP 3.3V / AUDIO 5V / AMPLIFIER'
add('U13','TLV62569DBVR','Package_TO_SOT_SMD:SOT-23-5',28,29,{'1':'POWER_BUS','2':'GND','3':'ESP_SW','4':'POWER_BUS','5':'ESP_FB'},F,names={'1':['EN','input'],'2':['GND','power_in'],'3':['SW','passive'],'4':['VIN','power_in'],'5':['FB','input']},source='https://www.ti.com/lit/ds/symlink/tlv62569.pdf',price=.80)
add('L4','2.2uH SWPA4030S 3A TARGET','Inductor_SMD:L_Sunlord_SWPA4030S',33,29,{'1':'ESP_SW','2':'ESP_3V3'},F,price=.30,note='Exact inductor Isat/Irms/DCR approval pending; not selected by inductance alone.')
c('C59','22u 16V',28,24,'POWER_BUS','GND',F,big=True)
c('C60','22u 16V',33,25,'ESP_3V3','GND',F,big=True)
r('R59','450k 1% 3.3V',28,33,'ESP_3V3','ESP_FB',F)
r('R60','100k 1%',28,36,'ESP_FB','GND',F)
copy('U9',85,10,F,{'BAT_SENSE_IN':'POWER_BUS','UPS_BACKUP_5V':'SYS_5V','UPS_BOOST_EN':'POWER_BUS'},3.29,basis='V3 TPS61230A page reference')
copy('L3',86,4,F,{'BAT_SENSE_IN':'POWER_BUS','UPS_BACKUP_5V':'SYS_5V'},.3697,basis='V3 selected 1uH power inductor page reference; dimensional approval pending')
c('C41','22u 16V',79,7,'POWER_BUS','GND',F,big=True)
c('C42','22u 16V',90,7,'SYS_5V','GND',F,big=True)
c('C43','22u 16V',95,7,'SYS_5V','GND',F,big=True)
c('C45','100n',82,3,'UPS_CBST','SYS_5V',F)
r('R40','499k 1%',82,12,'SYS_5V','UPS_BOOST_FB',F)
r('R41','100k 1%',86,12,'UPS_BOOST_FB','GND',F)
add('U14','MAX98357AETE+','Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.675x1.675mm',92,19,
 {'1':'I2S_SPK_DATA7','2':'AMP_GAIN','3':'GND','4':'AMP_SD','5':'','6':'','7':'SYS_5V','8':'SYS_5V','9':'SPK_PLUS','10':'SPK_MINUS','11':'GND','12':'','13':'','14':'I2S_SPK_WS16','15':'GND','16':'I2S_SPK_BCLK15','17':'GND'},F,
 names={str(n):[str(n),'power_in'if n in [3,7,8,11,15,17]else'output'if n in [9,10]else'no_connect'if n in [5,6,12,13]else'input']for n in range(1,18)},source='https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf',price=3,note='I2S A variant, mono left slot; QFN land and supplier part price pending exact package drawing approval.')
r('R61','0R LEFT CHANNEL',96,15,'SYS_5V','AMP_SD',F)
r('R62','0R 12dB',96,23,'AMP_GAIN','GND',F)
c('C61','10u',88,19,'SYS_5V','GND',F,big=True)
c('C62','100n',88,23,'SYS_5V','GND',F)
hdr('J15','SPEAKER BTL + / - NEVER GND',94,42,['SPK_PLUS','SPK_MINUS'],F)
hdr('J14','INMP441 MODULE 3V3 GND BCLK WS SD',94,49,['ESP_3V3','GND','I2S_MIC_BCLK14','I2S_MIC_WS13','I2S_MIC_DATA12'],F)
c('C26','100n MIC',88,51,'ESP_3V3','GND',F)

for ref,x,y,n in [('TP1',55,5,'POWER_BUS'),('TP4',30,40,'DEBUG_ESP_TX43'),('TP5',30,37,'DEBUG_ESP_RX44'),('TP6',54,5,'GND'),('TP7',16,50,'VIN_PROTECTED'),('TP8',51,52,'POWER_BUS'),('TP9',96,3,'SYS_5V'),('TP10',26,20,'ESP_3V3'),('TP11',44,57,'UPS_EXT_VALID')]:tp(ref,n,x,y,n,'07 TEST POINTS')
for ref,x,y in [('H1',4,20),('H2',96,4),('H3',4,71),('H4',96,71)]:add(ref,'M3','MountingHole:MountingHole_3.2mm_M3',x,y,{},'MECHANICAL',price=0)
for a,b in [((0,0),(100,0)),((100,0),(100,75)),((100,75),(0,75)),((0,75),(0,0))]:g.line(board,a,b,p.Edge_Cuts,.05)

# Preserve initial electrical anchors; adjust only overlapping small bodies on
# a local grid. No opposite-side SMT, no hidden courtyard exclusions.
fps={f.GetReference():f for f in board.GetFootprints()}
# Place switching-loop components as a group before packing low-speed parts.
# Copper and load qualification still follow; clearance alone is not loop proof.
anchors={
 'L1':(33,47.75,270),'C3':(30.5,43.5,0),'C4':(24.5,47.25,90),
 'C5':(24,51,90),'C6':(37.5,46,90),'C7':(37.5,50.5,270),
 'U13':(28,29,180),'L4':(33,28.05,0),'C59':(24,28.5,90),
 'C60':(37,28.05,90),'R59':(28,32,0),'R60':(25,32,0),
 'U9':(85,11.5,0),'L3':(85,5.1,270),'C41':(80.25,12.4,90),
 'C42':(90.75,10.96,0),'C43':(94.75,10.96,0),'C45':(88,14,90),
 'R40':(82,15.5,0),'R41':(82,18,0)}
for ref,(x,y,angle) in anchors.items():
    fps[ref].SetPosition(g.v(x,y));fps[ref].SetOrientationDegrees(angle)
    next(q for q in g.parts if q['ref']==ref).update(x=x,y=y,angle=angle)
def box(f):
    b=f.GetBoundingBox(False,False);return tuple(p.ToMM(z)for z in[b.GetLeft(),b.GetTop(),b.GetRight(),b.GetBottom()])
def overlap(a,b):return a[0]<b[2]+.06 and a[2]>b[0]-.06 and a[1]<b[3]+.06 and a[3]>b[1]-.06
fixed={r for r in fps if r.startswith(('U','J','H','L'))}|{'C8'}|set(anchors)
occupied=[box(fps[r])for r in fixed]
for part in sorted((q for q in g.parts if q['ref']not in fixed),key=lambda q:-(box(fps[q['ref']])[2]-box(fps[q['ref']])[0])*(box(fps[q['ref']])[3]-box(fps[q['ref']])[1])):
    f=fps[part['ref']];x,y=part['x'],part['y'];bb=box(f);rel=[bb[0]-x,bb[1]-y,bb[2]-x,bb[3]-y]
    candidates=[]
    for span in [24,48,72]:
        for dx in range(-span,span+1):
            for dy in range(-span,span+1):
                xx,yy=x+dx*.25,y+dy*.25;b=[xx+rel[0],yy+rel[1],xx+rel[2],yy+rel[3]]
                if b[0]<.7 or b[1]<.7 or b[2]>99.3 or b[3]>74.3 or any(overlap(b,o)for o in occupied):continue
                candidates.append((dx*dx+dy*dy,xx,yy,b))
        if candidates:break
    if not candidates:raise RuntimeError('Cannot place '+part['ref'])
    _,xx,yy,b=min(candidates);f.SetPosition(g.v(xx,yy));occupied.append(b);part.update(x=xx,y=yy)

project=json.loads((BASE/'voice_mainboard_v3.kicad_pro').read_text(encoding='utf8'))
project['meta']['filename']=PROJECT+'.kicad_pro'
project['board']['design_settings']['rules'].update(min_clearance=.2,min_track_width=.2,min_via_diameter=.6,min_through_hole_diameter=.3,min_via_annular_width=.15)
baseclass=project['net_settings']['classes'][0];baseclass.update(track_width=.2,via_diameter=.6,via_drill=.3)
project['net_settings']['classes']=[baseclass]
for name,width in [('POWER',.7),('RF',.8)]:
    cl=dict(baseclass);cl.update(name=name,track_width=width,priority=1);project['net_settings']['classes'].append(cl)
project['net_settings']['netclass_patterns']=[{'netclass':'POWER','pattern':n}for n in['VIN_DC','VIN_FUSED','VIN_PROTECTED','BAT_SENSE_IN','BAT_ALLOWED','ADAPTER_3V8','POWER_BUS','SYS_5V','ESP_3V3']]+[{'netclass':'RF','pattern':n}for n in['RF_ANT','RF_FEED']]
(ROOT/(PROJECT+'.kicad_pro')).write_text(json.dumps(project,indent=2)+'\n',encoding='utf8')
shutil.copy2(BASE/'voice_mainboard_v3.kicad_dru',ROOT/(PROJECT+'.kicad_dru'))
# Unused charger outputs are NC, not single-pin named nets.
for q in g.parts:
    if q['ref']=='U8':
        for number,net in list(q['pins'].items()):
            if net in ['DONE_OD','CHRG_OD']:
                q['pins'][number]=''
                for pd in fps['U8'].Pads():
                    if pd.GetNumber()==number:pd.SetNetCode(0)
p.SaveBoard(str(ROOT/(PROJECT+'.kicad_pcb')),board)
report={'revision':'V4-TWO-LAYER-INTEGRATED-20261122','status':'PLACEMENT / ROUTING AND VALIDATION REQUIRED','dimensions_mm':[100,75],'layers':2,'smt_sides':1,'parts':g.parts,
 'input_power':{'nominal_v':5,'range_at_connector_v':[4.5,5.5],'adapter_current_a':2,'connector_mm':[5.5,2.5],'primary_v':.8*(1+37.4/10),'battery':'external protected 1S pack >=5A with 10k/B3950 NTC','charge_current_a':.1,'full_power_or_transient_test_passed':False},
 'power_architecture':['VIN -> primary 3.792V buck -> TPS2117 VIN1','protected battery -> analog UV PMOS -> TPS2117 VIN2','TPS2117 POWER_BUS -> ML307 VBAT','POWER_BUS -> TLV62569 3.3V -> ESP32 + microphone','POWER_BUS -> TPS61230A 4.992V -> amplifier + optional radar','VIN -> TP4056 100mA -> battery'],
 'module_selection':{'model':'ML307C-DL','lcsc':'C48972417','user_authorized':True,
                     'pin_and_land_source':'sources/ml307c-dl-library.json','hardware_manual_verified':False,
                     'AT_and_USB_firmware_verified':False,'direct_R_substitution_qualified':False},
 'ups_controls':{'reference_bias_ohm':3300,'battery_uv':{'top_ohm':100000,'bottom_ohm':19600,'feedback_ohm':2200000,'pullup_ohm':10000},
                 'external_priority':{'top_ohm':100000,'bottom_ohm':18200,'feedback_ohm':10000000,'pullup_ohm':10000},
                 'primary_PG_qualified':True,'battery_to_modem_minimum_v':3.4,'full_UPS_qualified':False},
 'user_price_assumptions':{'ML307C-DL':10,'ESP32-S3-WROOM-1-N8R8':12,'basis':'user specified procurement costs, supplier order not confirmed'},
 'microphone':'external INMP441 module, included in cost; placement at enclosure acoustic port',
 'gpio_contract':{'modem_tx':17,'modem_rx':18,'modem_dtr':4,'mic_bclk':14,'mic_ws':13,'mic_sd':12,'amp_bclk':15,'amp_ws':16,'amp_sd':7,'radar_rx':6,'radar_tx':8,'button':0,'battery_adc':2,'battery_sample_enable':9,'external_present_n':10,'modem_pwrkey':11,'modem_reset':21,'charger_disable':38,'ttl_tx':43,'ttl_rx':44},
 'assembly_open_items':['C-DL manufacturer HW manual, voltage/timing, AT commands and USB firmware descriptors','Exact N8R8 supplier cost and PSRAM timing compatibility','MAX98357A QFN recommended land/paste drawing','SIM/socket/capacitor/jack physical fit','Power-loop, input-low voltage, RF/USB and full prototype qualification','New GPIO battery/pwrkey/charger functions not added to official-protocol firmware'],
 'target_50_achieved':False,'manufacturing_ready':False,'firmware_modified':False}
(ROOT/'design.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'cost/part-price-inputs.json').write_text(json.dumps(prices,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Created V4:',len(g.parts),'footprints;',len(g.nets),'nets; two-layer / all populated SMT on front; unqualified.')
