"""Recalculate battery controls and run actual ngspice subcircuit tests.

Only resistor networks and ideal control switches are modeled. No vendor
converter/charger/ML307 macro-model or cell electrochemistry is invented.
"""
from pathlib import Path
import hashlib, itertools, json, math, re, sys, os
import pcbnew as p
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
sys.path.insert(0,str(ROOT.parent/'voice_mainboard_v2'))
from spice_runtime import run
FILE=Path(os.environ.get('A18_AUDIT_BOARD',str(ROOT/'voice_mainboard_v8_a18.kicad_pcb'))).resolve()
ROOT=FILE.parent
OUT=ROOT/'exports/simulation';OUT.mkdir(parents=True,exist_ok=True)
READ_ONLY=os.environ.get('A18_AUDIT_READ_ONLY')=='1'
b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()}
def val(r):
    m=re.match(r'([0-9.]+)([kM]?)',fps[r].GetValue());assert m,r
    return float(m[1])*{'':1,'k':1000,'M':1000000}[m[2]]
def nets(r):return {d.GetNumber():d.GetNetname()for d in fps[r].Pads()if d.GetNumber()}
expected={'U16':{'1':'BAT_TEMP','2':'CHG_PROG','3':'GND','4':'VIN_PROTECTED','5':'BAT_SENSE_IN','6':'CHG_FULL_N','7':'CHG_ACTIVE_N','8':'CHG_CE','9':'GND'},
 'U18':{'1':'GND','2':'SYS_5V','3':'VIN_PROTECTED','4':'UPS_PR1','5':'VIN_PROTECTED','6':'BAT_BOOST_5V','7':'SYS_5V','8':'SUPPLY_BAT_N47'},
 'U17':{'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NEG','4':'GND','5':'GND'},
 'Q7':{'1':'CHG_DISABLE_IO38','2':'GND','3':'CHG_CE'},'J23':{'1':'BAT_SENSE_IN','2':'CELL_NEG','3':'CELL_NTC'}}
for r,e in expected.items():assert nets(r)==e,(r,nets(r))

changes={'R64':('12k 1%',12000),'R66':('200k 1%',200000)}
schema=FILE.with_suffix('.kicad_sch')
text=schema.read_text(encoding='utf-8')
# Locate the entire symbol containing the reference using balanced parentheses,
# preserving UUIDs, wiring and all other symbols.
def symbol_span(src,ref):
    # The first occurrence belongs to the embedded library; update the placed
    # symbol instance, whose Reference property is the final occurrence.
    mark=src.rindex('(property "Reference" "'+ref+'"')
    starts=[];stack=[];quoted=False;escape=False
    for i,ch in enumerate(src[:mark]):
        if quoted:
            if escape:escape=False
            elif ch=='\\':escape=True
            elif ch=='"':quoted=False
            continue
        if ch=='"':quoted=True
        elif ch=='(':stack.append(i)
        elif ch==')':stack.pop()
    start=next(i for i in reversed(stack)if src.startswith('(symbol\n',i)or src.startswith('(symbol ',i))
    depth=0;quoted=False;escape=False
    for i in range(start,len(src)):
        ch=src[i]
        if quoted:
            if escape:escape=False
            elif ch=='\\':escape=True
            elif ch=='"':quoted=False
            continue
        if ch=='"':quoted=True
        elif ch=='(':depth+=1
        elif ch==')':
            depth-=1
            if depth==0:return start,i+1
    raise AssertionError('Unclosed schematic symbol')
for r,(label,value)in changes.items():
    if READ_ONLY:
        assert fps[r].GetValue()==label and val(r)==value,(r,'unexpected resistance in read-only audit')
        continue
    old=fps[r].GetValue();a,z=symbol_span(text,r);segment=text[a:z]
    segment,n=re.subn(r'(\(property "Value" ")[^"]*(")',lambda m:m[1]+label+m[2],segment,count=1);assert n==1
    text=text[:a]+segment+text[z:];fps[r].SetValue(label)
if not READ_ONLY:
    schema.write_text(text,encoding='utf-8')
    p.SaveBoard(str(FILE),b)
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
for q in data['parts']:
    if q['ref']in changes:
        q.update(value=changes[q['ref']][0],lcsc=None,source='',mpn=changes[q['ref']][0],price_basis='new resistance; exact procurement part pending')
data['ups_controls'].update(charge_current_ma=100,assumed_pack_NTC='10k B3950, 1%')
if not READ_ONLY:
    (ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

rt,rb=val('R65'),val('R66')
def ntc(temp,r25=10000,beta=3950):return r25*math.exp(beta*(1/(temp+273.15)-1/298.15))
def threshold(ratio,top=rt,bottom=rb,r25=10000,beta=3950):
    parallel=top*ratio/(1-ratio);assert bottom>parallel
    r=1/(1/parallel-1/bottom)
    return 1/(1/298.15+math.log(r/r25)/beta)-273.15
corners={k:[]for k in ['cold','hot']}
for signs in itertools.product([-1,1],repeat=4):
    for ratio,key in [(.8,'cold'),(.45,'hot')]:
        corners[key].append(threshold(ratio,rt*(1+.01*signs[0]),rb*(1+.01*signs[1]),10000*(1+.01*signs[2]),3950*(1+.01*signs[3])))
cases=[]
for name,temp,ntcr in [('cold_minus5',-5,ntc(-5)),('room25',25,ntc(25)),('hot45',45,ntc(45)),('NTC_open',None,1e15)]:
    lines=['Vext ext 0 5','Vgpio pause 0 PWL(0 0 .004 0 .004001 3.3 .008 3.3 .008001 0 .012 0)',
      f'Rce ext ce {val("R68")}',f'Rgate pause 0 {val("R69")}',
      'Sce ce 0 pause 0 IDEAL','.model IDEAL SW(Ron=2 Roff=1e12 Vt=1.2 Vh=0)',
      f'RtempTop ext temp {rt}',f'RtempBottom temp 0 {rb}',f'Rntc temp 0 {ntcr}',
      f'RprTop ext pr {val("R70")}',f'RprBottom pr 0 {val("R71")}',
      'Vcell cell 0 4.2',f'RadcTop cell adc {val("R17")}',f'RadcBottom adc 0 {val("R18")}',
      'Cadc adc 0 100n','.tran 2u .012']
    vectors,_=run('a18_'+name,lines,['v(ce)','v(temp)','v(pr)','v(adc)'],OUT)
    def at(sig,t):return vectors[sig][min(range(len(vectors['time'])),key=lambda i:abs(vectors['time'][i]-t))]
    ratio=at('v(temp)',.003)/5;allow=.45<=ratio<=.8
    assert allow==(name=='room25'),(name,ratio)
    assert at('v(ce)',.003)>4.9 and at('v(ce)',.006)<.01
    adc=at('v(adc)',.012);assert adc<3.3
    cases.append({'case':name,'temperature_C':temp,'TEMP_VCC_ratio':ratio,'charge_allowed_by_nominal_TEMP':allow,
      'CE_with_GPIO_low_v':at('v(ce)',.003),'CE_with_GPIO_high_v':at('v(ce)',.006),'battery_ADC_4v2_v':adc,
      'PR_external5v_v':at('v(pr)',.003),'ngspice_completed':True,'passes_model_expectation':True})
report={'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'schematic_sha256':hashlib.sha256(schema.read_bytes()).hexdigest(),
 'scope':'ngspice resistor/ideal CE switch model and PCB pin-map audit; NOT full-board or vendor converter/charger simulation',
 'changed_values':{r:v[0]for r,v in changes.items()},'nominal_charge_current_ma':1200/val('R64')*1000,
 'nominal_temperature_window_C':[threshold(.8),threshold(.45)],'R_R25_beta_1pct_corner_window_C':{k:[min(v),max(v)]for k,v in corners.items()},
 'IC_temperature_threshold_tolerance_included':False,'cell_spec_and_NTC_verified':False,'cases':cases,
 'no_battery_external_path_independent':True,'raw_cell_negative_is_GND':False,'80_70_percent_control_implemented':False,
 'full_board_simulated':False,'actual_2A_transient_or_thermal_qualified':False,'manufacturing_ready':False}
(OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k]for k in ['changed_values','nominal_charge_current_ma','nominal_temperature_window_C','R_R25_beta_1pct_corner_window_C','cases','full_board_simulated']},ensure_ascii=False,indent=2))
