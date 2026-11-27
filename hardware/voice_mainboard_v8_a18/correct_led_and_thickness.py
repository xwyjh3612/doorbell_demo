"""Correct an actual LED rail corner mismatch and the A18 1.2mm board thickness."""
from pathlib import Path
import hashlib,json,re,shutil,sys
import pcbnew as p
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO/'build/cad-tools/route-python'))
from shapely.geometry import Point,LineString,box
FILE=ROOT/'voice_mainboard_v8_a18.kicad_pcb';SCH=ROOT/'voice_mainboard_v8_a18.kicad_sch'
snap=ROOT/'history/before-led-corner-correction';snap.mkdir(exist_ok=True)
for f in [FILE,SCH,ROOT/'design.json']:shutil.copy2(f,snap/f.name)
b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()}
region=box(30,6,43,18);removed=[]
for t in list(b.GetTracks()):
    if t.GetNetname()!='ESP_3V3':continue
    if isinstance(t,p.PCB_VIA):sh=Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y))
    else:
        a,z=t.GetStart(),t.GetEnd();sh=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))])
    if sh.intersects(region):removed.append(t);b.Remove(t)
for ref,num in [('D2','4'),('C74','1')]:
    next(d for d in fps[ref].Pads()if d.GetNumber()==num).SetNet(b.FindNet('MODEM_3V8'))
b.GetDesignSettings().SetBoardThickness(p.FromMM(1.2))
text=SCH.read_text(encoding='utf-8')
for label_uuid in ['fea89835-b01f-57ee-b09f-7eca4781989a','011c993d-0953-5f19-acf8-2cb29d11530a']:
    pattern=r'\(global_label "ESP_3V3"[^\n]*\(uuid '+label_uuid+r'\)\)'
    text,n=re.subn(pattern,lambda m:m[0].replace('"ESP_3V3"','"MODEM_3V8"',1),text);assert n==1
SCH.write_text(text,encoding='utf-8')
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
for q in data['parts']:
    if q['ref']=='D2':q['pins']['4']='MODEM_3V8';q['note']+=' A18: powered from regulated3.8V; ESP rail low corner is below vendor3.3V minimum. VIH0.55VDD is compatible with ESP GPIO.'
    if q['ref']=='C74':q['pins']['1']='MODEM_3V8'
data['mechanical']['board_thickness_mm']=1.2
data['indicators']['rgb']['rail']='MODEM_3V8'
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'exports/led-rail-and-thickness-correction.json').write_text(json.dumps({
    'removed_old_ESP_supply_copper_items':len(removed),'new_LED_supply':'MODEM_3V8',
    'LED_vendor_VDD_range_V':[3.3,5.3],'ESP_supply_calculated_min_V':3.212253528,
    'new_supply_calculated_min_max_V':[3.745113266,3.872204381],
    'VIH_coefficient':.55,'GPIO_high_min_assumption_coefficient':.8,
    'logic_high_margin_V':.8*3.212253528-.55*3.872204381,
    'board_thickness_mm':1.2,'new_supply_not_yet_dynamically_qualified':True,
    'sources':['../voice_mainboard_v7/sources/rgb-20261124/WS2812B-2020-V6.txt pages3/4','A18 user mechanical drawing1.20 annotation'],
    'manufacturing_ready':False},indent=2),encoding='utf-8')
for t in removed:t.thisown=False
print('Corrected LED supply and1.2mm board thickness; source/copper revalidation required')
