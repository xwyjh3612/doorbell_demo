"""Build the integrated-UPS revision from the saved V2 engineering board.

Does not modify V2 or release fabrication files. Re-route and validate V3 after
this placement/net change. Manufacturer data, not a retail UPS module, defines
the charging/boost/mux circuit.
"""
from pathlib import Path
import importlib.util, json, shutil
import pcbnew as pcb

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'voice_mainboard_v2'
ROOT.mkdir(exist_ok=True)
(ROOT/'exports').mkdir(exist_ok=True)
LOCAL=ROOT/'VoiceV2.pretty';LOCAL.mkdir(exist_ok=True)
for f in (BASE/'VoiceV2.pretty').glob('*.kicad_mod'):shutil.copy2(f,LOCAL/f.name)
for name in ['TI_RNS0007A','TI_DRL0008A']:
    shutil.copy2(ROOT.parent/'voice_carrier_v1/Voice.pretty'/f'{name}.kicad_mod',LOCAL/f'{name}.kicad_mod')
spec=importlib.util.spec_from_file_location('v2gen',BASE/'generate_design.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
g.ROOT=ROOT;g.LOCAL=LOCAL
g.board=pcb.LoadBoard(str(BASE/'voice_mainboard_v2.kicad_pcb'))
g.nets={n.GetNetname():n for n in g.board.GetNetsByNetcode().values() if n.GetNetname()}
data=json.loads((BASE/'design.json').read_text(encoding='utf8'))
g.parts=data['parts']
board=g.board
initial_footprints={f.GetReference():f for f in board.GetFootprints()}
initial_zones=list(board.Zones())
from input_jack import replace as replace_jack
replace_jack(board,g.parts,ROOT)
# Jack replacement removes its own old pad copper. Snapshot only surviving
# tracks afterward; do not remove/access freed SWIG track wrappers twice.
initial_tracks=list(board.GetTracks())

def drop(ref):
    f=initial_footprints[ref]
    board.Remove(f);g.parts[:]=[p for p in g.parts if p['ref']!=ref]

def custom_terminal():
    # DEGSON DG350 drawing: 3.5mm pitch, 0.80mm pin, 1.00mm finished hole.
    # UL rating 7A, accepts 24..18AWG. Body includes 0.5mm side flanges.
    fp=pcb.FOOTPRINT(board);fp.SetFPID(pcb.LIB_ID('VoiceV2','DG350_3.5_2P'))
    for n,x in [(1,0),(2,3.5)]:
        p=pcb.PAD(fp);p.SetNumber(str(n));p.SetPosition(g.v(x,0));p.SetSize(g.v(2,2))
        p.SetDrillSize(g.v(1,1));p.SetAttribute(pcb.PAD_ATTRIB_PTH)
        p.SetShape(pcb.PAD_SHAPE_RECT if n==1 else pcb.PAD_SHAPE_CIRCLE)
        layers=pcb.LSET.AllCuMask();layers.AddLayer(pcb.F_Mask);layers.AddLayer(pcb.B_Mask)
        p.SetLayerSet(layers);fp.Add(p)
    for layer,margin,width in [(pcb.F_Fab,0,.1),(pcb.F_CrtYd,.5,.05)]:
        x1,x2,y1,y2=-2.25-margin,5.75+margin,-3.4-margin,3.1+margin
        for a,b in [((x1,y1),(x2,y1)),((x2,y1),(x2,y2)),((x2,y2),(x1,y2)),((x1,y2),(x1,y1))]:g.line(fp,a,b,layer,width)
    fp.SetLibDescription('DG350-3.5-02P-14-00A(H), C2760668; DEGSON manufacturer drawing FOR-1351 Rev1.0. 7A UL. Pin1 battery+, pin2 ground.')
    g.io.FootprintSave(str(LOCAL),fp)

# Future plug-in power/status connectors are replaced by real on-board UPS.
for ref in ['J2','J3','J4','J5']:drop(ref)
print('V3: removed obsolete headers',flush=True)
# Their old left/bottom copper must not be reused under new power components.
# Every removed segment is recorded; unaffected RF/USB/regulator copper stays.
removed=[]
for t in initial_tracks:
    points=[t.GetPosition()] if isinstance(t,pcb.PCB_VIA) else [t.GetStart(),t.GetEnd()]
    if min(pcb.ToMM(p.x)for p in points)<30 and max(pcb.ToMM(p.x)for p in points)>2 and max(pcb.ToMM(p.y)for p in points)>43.5:
        removed.append(dict(net=t.GetNetname(),type=type(t).__name__))
        board.Remove(t)
for z in initial_zones:board.Remove(z)
print('V3: removed obsolete copper',len(removed),flush=True)

custom_terminal()
print('V3: created battery terminal',flush=True)
group='07 INTEGRATED UPS / BATTERY / CHARGING'
add=lambda *a,**kw:g.add(*a,group=group,**kw)
def r(ref,val,x,y,a,b,angle=0):return g.r(ref,val,x,y,a,b,group,angle)
def c(ref,val,x,y,a,b,big=False,angle=0):return g.c(ref,val,x,y,a,b,group,angle,big=big)

# Battery pack includes an independent >=5A protection PCB and 10k/B3950 NTC.
# The mainboard supplies normal UV hysteresis, charging and temperature control.
add('J2','BATTERY PACK 1S 4.2V >=5A; PIN1+ PIN2GND','VoiceV2:DG350_3.5_2P',7,65,
    {'1':'BAT_SENSE_IN','2':'GND'},source='https://item.szlcsc.com/2882221.html',
    note='C2760668, DEGSON DG350-3.5-02P-14-00A(H). UL 7A. Use protected battery-pack leads rated >=5A; never reverse polarity. J4 remains only the NTC connection.')
g.hdr('J4','PACK NTC 10k B3950',6,56,['NTC_PACK','GND'],group,90)

# Charger: modest 100mA default; can be inhibited by ESP GPIO38 during a call.
# CE is pulled to local VIN, never fed from an ESP pin when VIN is absent.
add('U8','TP4056 TPOWER C382139','Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.29x3mm',10,51,
    {'1':'UPS_TEMP','2':'UPS_CHG_PROG','3':'GND','4':'VIN_PROTECTED','5':'BAT_SENSE_IN','6':'DONE_OD','7':'CHRG_OD','8':'UPS_CHG_CE','9':'GND'},
    names={'1':['TEMP','input'],'2':['PROG','passive'],'3':['GND','power_in'],'4':['VCC','power_in'],'5':['BAT','passive'],'6':['STDBY','open_collector'],'7':['CHRG','open_collector'],'8':['CE','input'],'9':['EP_GND','power_in']},
    source='https://item.szlcsc.com/354934.html',note='TPOWER formula 1100/RPROG(A): 11k = 100mA. Main load is isolated from charger BAT by the backup converter/mux. Charging inhibition GPIO38 is a hardware provision; current firmware does not drive it yet.')
r('R35','11k 1%',7,46,'UPS_CHG_PROG','GND')
r('R36','9.1k 1%',8,58,'VIN_PROTECTED','UPS_TEMP')
r('R37','3.3k 1%',11,58,'UPS_TEMP','NTC_PACK')
c('C38','10u 10V',6,51,'VIN_PROTECTED','GND',big=True,angle=90)
c('C39','10u 10V',15,53,'BAT_SENSE_IN','GND',big=True,angle=90)
r('R38','100k',15,46,'VIN_PROTECTED','UPS_CHG_CE')
g.mos('Q7','2N7002K-7 DIODES',20,46,'CHG_DISABLE_IO38','GND','UPS_CHG_CE',group)
r('R39','100k',23,47,'CHG_DISABLE_IO38','GND')

# Backup boost always ready when battery is above the hardware UV hysteresis.
add('U9','TPS61230ARNSR','VoiceV2:TI_RNS0007A',17,62,
    {'1':'UPS_CBST','2':'UPS_BOOST_EN','3':'UPS_BOOST_FB','4':'BAT_SENSE_IN','5':'UPS_SW','6':'GND','7':'UPS_BACKUP_5V'},angle=180,
    names={'1':['CBST','passive'],'2':['EN','input'],'3':['FB','input'],'4':['VIN','power_in'],'5':['SW','passive'],'6':['GND','power_in'],'7':['VOUT','power_out']},
    source='https://www.ti.com/lit/ds/symlink/tps61230a.pdf',note='5V/2A backup target, not a completed load/thermal qualification. 6A peak switch rating is not output current. UV hardware controls EN; no software wake delay.')
add('L3','MWSA0603S-1R0MT C112125','Inductor_SMD:L_Sunlord_MWSA0603S',11,57,
    {'1':'BAT_SENSE_IN','2':'UPS_SW'},angle=0,
    source='https://item.szlcsc.com/113356.html',
    note='Sunlord MWSA-S catalog Rev2025/8/29 page6:1uH+-20%,DCR7.4mOhm max,Isat12A rated/15Atyp,Irms10A rated/12Atyp. Page2 landI2.35/J3.7/H3.5 matches KiCad MWSA0603S footprint. Verify production spec/derating, never substitute SWPA solely by inductance.')
c('C40','22u 16V X5R',17,57,'BAT_SENSE_IN','GND',big=True)
c('C41','22u 16V X5R',15.5,60.5,'BAT_SENSE_IN','GND',big=True)
c('C42','22u 16V X5R',20,62,'UPS_BACKUP_5V','GND',big=True,angle=90)
c('C43','22u 16V X5R',23,62,'UPS_BACKUP_5V','GND',big=True,angle=90)
c('C44','22u 16V X5R',17,66,'UPS_BACKUP_5V','GND',big=True)
c('C45','10n',21.5,59.5,'UPS_CBST','UPS_SW')
r('R40','316k 0.1%',19,69,'UPS_BACKUP_5V','UPS_BOOST_FB')
r('R41','100k 0.1%',19,72,'UPS_BOOST_FB','GND')

# Mux priority is driven by a comparator, avoiding +/-8% internal PR1 threshold
# being used as a precision raw-input undervoltage boundary.
add('U10','TPS2117DRLR','VoiceV2:TI_DRL0008A',18,50,
    {'1':'GND','2':'POWER_REG_5V','3':'VIN_PROTECTED','4':'UPS_EXT_VALID','5':'UPS_CTL_VCC','6':'UPS_BACKUP_5V','7':'POWER_REG_5V','8':'UPS_PG_OD'},
    names={'1':['GND','power_in'],'2':['VOUT','power_out'],'3':['VIN1','power_in'],'4':['PR1','input'],'5':['MODE','input'],'6':['VIN2','power_in'],'7':['VOUT','power_out'],'8':['ST','open_collector']},
    source='https://www.ti.com/lit/ds/symlink/tps2117.pdf',note='Comparator-driven manual selection, MODE biased from diode-OR UPS_CTL_VCC so it stays high after adapter removal. Raw adapter -> VIN1; ready backup -> VIN2. Both outputs must never be directly paralleled. Output is POWER_BUS input, which is raw-adapter voltage normally and approx5V on battery; downstream U2/U6 independently regulate.')
c('C46','1u 10V',22,51,'VIN_PROTECTED','GND')
c('C47','1u 10V',22,54,'UPS_BACKUP_5V','GND')
add('C48','470u 10V LOW ESR; PART PENDING','Capacitor_SMD:CP_Elec_8x10',24,69,
    {'1':'POWER_REG_5V','2':'GND'},note='Mux hold-up reservoir. Exact ripple/ESR and total inrush capacitance need selection and test. 470u is not proof that the real switch transient stays inside rail limits.')
c('C53','10u 16V X5R',24,50,'POWER_REG_5V','GND',big=True)

# Low-power analog control supply exists on either raw input or protected cell.
# TLV7042 has rail-to-rail inputs and 1.6V minimum supply. This keeps the
# comparator specified when cell/diode drop reduce the analog supply.
g.add('D5','BAT54C,215','Package_TO_SOT_SMD:SOT-23',73,61,
    {'1':'VIN_PROTECTED','2':'BAT_SENSE_IN','3':'UPS_CTL_VCC'},'08 UPS THRESHOLDS / STATUS',
    names={'1':['A1','passive'],'2':['A2','passive'],'3':['K_COMMON','passive']},source='https://item.szlcsc.com/38684.html')
add('U11','LM393LVDGKR TI C3659248','Package_SO:VSSOP-8_3x3mm_P0.65mm',78,62,
    {'1':'UPS_BOOST_EN','2':'UPS_REF_0V62','3':'UPS_BAT_UV_SENSE','4':'GND','5':'UPS_EXT_SENSE','6':'UPS_REF_0V62','7':'UPS_EXT_VALID','8':'UPS_CTL_VCC'},
    names={'1':['OUT_A','open_collector'],'2':['IN_A_NEG','input'],'3':['IN_A_POS','input'],'4':['GND','power_in'],'5':['IN_B_POS','input'],'6':['IN_B_NEG','input'],'7':['OUT_B','open_collector'],'8':['VCC','power_in']},
    source='https://www.ti.com/lit/ds/symlink/lm393lv.pdf',
    note='TI LM393LVDGKR C3659248, open-drain dual comparator, rail-to-rail input,1.65-5.5V supply,DGK VSSOP8. +/-3mV full-temperature offset, no specified internal hysteresis. Use LV part only; ordinary LM393 is not a substitute. Public price1.0033 CNY, stock1338 checked20261122.')
add('U12','TLV431BIDBZR TI C398375','Package_TO_SOT_SMD:SOT-23',86,63,
    {'1':'UPS_REF_1V24','2':'UPS_REF_1V24','3':'GND'},
    names={'1':['REF','input'],'2':['K','passive'],'3':['A','passive']},source='https://www.ti.com/lit/ds/symlink/tlv431.pdf')
r('R42','3.3k',89,63,'UPS_CTL_VCC','UPS_REF_1V24')
r('R43','10k 0.1%',85,59,'UPS_REF_1V24','UPS_REF_0V62')
r('R44','10k 0.1%',89,59,'UPS_REF_0V62','GND')
c('C49','1n C0G',89,67,'UPS_REF_0V62','GND')
c('C50','100n',74,64,'UPS_CTL_VCC','GND')
r('R45','499k 0.1%',71,58,'BAT_SENSE_IN','UPS_BAT_UV_SENSE')
r('R46','102k 0.1%',70,62,'UPS_BAT_UV_SENSE','GND')
r('R47','2.4M 1%',72,66,'UPS_BOOST_EN','UPS_BAT_UV_SENSE')
r('R48','10k',70,69,'BAT_SENSE_IN','UPS_BOOST_EN')
r('R49','1M 1%',74,69,'UPS_BOOST_EN','GND')
c('C51','10n',78,69,'UPS_BAT_UV_SENSE','GND')
r('R50','54.9k 0.1%',83,56,'VIN_PROTECTED','UPS_EXT_SENSE')
r('R51','10k 0.1%',86,56,'UPS_EXT_SENSE','GND')
r('R52','3.9M 1%',82,69,'UPS_EXT_VALID','UPS_EXT_SENSE')
r('R53','10k',82,72,'UPS_CTL_VCC','UPS_EXT_VALID')
r('R54','1M 1%',86,72,'UPS_EXT_VALID','GND')
c('C52','1n C0G',89,71,'UPS_EXT_SENSE','GND')

byref={f.GetReference():f for f in board.GetFootprints()}
for p in g.parts:
    ref=p['ref']
    if ref in ['U8','Q7','J2','J4','R35','R36','R37','R38','R39','C38','C39']:
        p['group']='07 BATTERY PACK / CHARGER / NTC'
    elif ref in ['U9','U10','L3','R40','R41','C53',*[f'C{k}'for k in range(40,49)]]:
        p['group']='08 BACKUP BOOST / AUTOMATIC POWER MUX'
    elif ref in ['U11','U12','D5',*[f'R{k}'for k in range(42,55)],*[f'C{k}'for k in range(49,53)]]:
        p['group']='09 HARDWARE UV HYSTERESIS / SOURCE THRESHOLD'
    if p['ref'] in ['R22','R23','R24']:
        p['dnp']=False;p['value']='10k';byref[p['ref']].SetDNP(False);byref[p['ref']].SetValue('10k')
    if p['ref']=='JP4':
        p['value']='UPS NORMAL 2-3 / DIRECT DIAGNOSTIC 1-2';byref['JP4'].SetValue(p['value'])
        p['note']='One shunt only. Production/normal2-3 uses onboard automatic UPS; diagnostic1-2 bypasses it. No two shunts.'
    if p['ref']=='J13':
        p['pins']['28']='CHG_DISABLE_IO38';p['note']='Pins1-27 unchanged; pin28 non-strapping GPIO38 provision for charge inhibition (high disables); pin29NC; pin30GND. Current firmware charge-control support pending.'
        next(pd for pd in byref['J13'].Pads()if pd.GetNumber()=='28').SetNet(g.net('CHG_DISABLE_IO38'))
    if p['ref']=='U10':p['names']['7']=['VOUT_DUPLICATE','passive']

from place_ups import place
placement=place(board,g.parts)
board.BuildConnectivity()
pcb.SaveBoard(str(ROOT/'voice_mainboard_v3.kicad_pcb'),board)
data.update(revision='V3-INTEGRATED-UPS-20261122',status='UPS PLACEMENT / ROUTING IN PROGRESS - NOT FOR FABRICATION',parts=g.parts,
    ups_chip='TPOWER TP4056 + TI TPS61230A + TI TPS2117; analog UV/external thresholds',
    ups_mounting='Integrated mainboard circuit, no retail UPS module',ups_reserved_region_mm=None,
    manufacturing_ready=False,firmware_modified=False,
    battery='Protected1S4.2V Li-ion pack, >=5A discharge,10k/B3950NTC. Pack cell/protection/NTC external; charger/normalUV/mux/boost on mainboard.')
data['power_architecture'].update(normal_shunts=['JP4 2-3','JP1 1-2','J19 1-2','JP3 1-2'],backup_boost='U9 TPS61230A',mux='U10 TPS2117',charger='U8 TP4056',ups_integrated=True)
data['ups_controls']={'battery_uv':{'reference_v':.62,'top_ohm':499000,'bottom_ohm':102000,'feedback_ohm':2400000,'en_pullup_ohm':10000,'en_pulldown_ohm':1000000},
    'external_priority':{'reference_v':.62,'top_ohm':54900,'bottom_ohm':10000,'feedback_ohm':3900000,'pullup_ohm':10000,'pulldown_ohm':1000000},
    'charge_current_A':.1,'charge_disable_gpio':38,'default_charge_enabled':True,'charging_inhibit_firmware_implemented':False,'ntc':{'r25_ohm':10000,'beta_K':3950,'top_ohm':9100,'series_ohm':3300},
    'boost_voltage_reference_V':1.2,'boost_feedback_top_ohm':316000,'boost_feedback_bottom_ohm':100000,'target_boost_V':4.992,
    'validated_on_hardware':False,'exact_inductor_capacitor_selection_complete':False}
data['ups_controls']['comparator']={'part':'LM393LVDGKR','lcsc':'C3659248','supply_range_v':[1.65,5.5],'rail_to_rail_input':True,'output':'open-drain','offset_full_temperature_v':[-.003,.003],'internal_hysteresis_specified':False}
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'exports/integration-change.json').write_text(json.dumps({'base':'V2','removed_future_headers':['J2','J3','J4','J5'],'new_battery_terminal':'J2','new_ntc_header':'J4','removed_copper_segments':len(removed),'removed_copper_by_net':removed,'manufacturing_ready':False},ensure_ascii=False,indent=2),encoding='utf8')
(ROOT/'exports/ups-placement.json').write_text(json.dumps(placement,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
pro=json.loads((BASE/'voice_mainboard_v2.kicad_pro').read_text(encoding='utf8'))
pro['meta']['filename']='voice_mainboard_v3.kicad_pro'
pro['net_settings']['netclass_patterns'] += [{'netclass':'POWER','pattern':n}for n in ['BAT_SENSE_IN','UPS_BACKUP_5V','UPS_SW','UPS_CTL_VCC']]
(ROOT/'voice_mainboard_v3.kicad_pro').write_text(json.dumps(pro,indent=2)+'\n',encoding='utf8')
print('Created V3 integrated UPS engineering design:',len(g.parts),'footprints;',len(list(board.GetTracks())),'preserved copper items. Routing/part qualification pending.')
