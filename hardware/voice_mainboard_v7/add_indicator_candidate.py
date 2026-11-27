"""Create separate LED candidate; fix the verified GPIO38 pad mapping.

Preserve prior board and reports. Incremental schematic edits keep original
UUIDs; KiCad native DRC/ERC/parity must be run on this candidate.
"""
import collections,hashlib,json,re,shutil,sys,types,uuid
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=ROOT/'indicator_revision';OUT.mkdir(exist_ok=True)
FILE=OUT/'voice_mainboard_v7.kicad_pcb'
# After promotion, reconstruct from the retained pre-RGB baseline.
BASE=ROOT/'history/20261124-before-rgb'
if not (BASE/FILE.name).exists():BASE=ROOT
for name in ['voice_mainboard_v7.kicad_pcb','voice_mainboard_v7.kicad_sch','voice_mainboard_v7.kicad_pro','voice_mainboard_v7.kicad_dru','VoiceV2.kicad_sym','fp-lib-table','sym-lib-table','design.json']:
    shutil.copy2(BASE/name if (BASE/name).exists() else ROOT/name,OUT/name)
shutil.copytree(ROOT/'VoiceV2.pretty',OUT/'VoiceV2.pretty',dirs_exist_ok=True)
(OUT/'exports').mkdir(exist_ok=True)
source=(ROOT.parent/'voice_mainboard_v3/route_helpers.py').read_text(encoding='utf-8')
source=source.replace('    obstacle=unary_union(obstacles)', '''    for zone in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not zone.GetIsRuleArea() and zone.IsOnLayer(layer) and zone.GetNetname() not in ['GND',net]:
            for i in range(zone.Outline().OutlineCount()):
                ring=zone.Outline().COutline(i)
                obstacles.append(Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]).buffer(width/2+.205))
        if not zone.GetIsRuleArea() or not zone.IsOnLayer(layer):continue
        for i in range(zone.Outline().OutlineCount()):
            ring=zone.Outline().COutline(i)
            obstacles.append(Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]).buffer(width/2+.005))
    obstacle=unary_union(obstacles)''')
source=source.replace('    blocked=unary_union(all_obstacles);fblocked=unary_union(front)', '''    for zone in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not zone.GetIsRuleArea() and zone.GetNetname() not in ['GND',net]:
            for zi in range(zone.Outline().OutlineCount()):
                ring=zone.Outline().COutline(zi)
                sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
                all_obstacles.append(sh.buffer(diameter/2+.205))
                if zone.IsOnLayer(layer):front.append(sh.buffer(neck/2+.205))
        if not zone.GetIsRuleArea():continue
        for zi in range(zone.Outline().OutlineCount()):
            ring=zone.Outline().COutline(zi)
            sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
            all_obstacles.append(sh.buffer(diameter/2+.005))
            if zone.IsOnLayer(layer):front.append(sh.buffer(neck/2+.005))
    blocked=unary_union(all_obstacles);fblocked=unary_union(front)''')
sys.argv=[__file__,str(FILE)]
r=types.ModuleType('led_candidate_router');exec(compile(source,'led_candidate_router','exec'),r.__dict__)
b=r.board;held=[]
multi=(ROOT.parent/'voice_mainboard_v3/route_multilayer.py').read_text(encoding='utf-8')
multi=multi.replace('layers=[p.F_Cu,p.B_Cu,p.In2_Cu]','layers=[p.F_Cu,p.B_Cu]').replace('range(3)','range(len(layers))')
multi=multi.replace('from shapely.geometry import Point,LineString','from shapely.geometry import Point,LineString,Polygon')
multi=multi.replace('        shapes=[]','''        shapes=[]
        for zone in [*b.Zones(), *[z for fp in b.GetFootprints() for z in fp.Zones()]]:
            if not zone.GetIsRuleArea() and zone.IsOnLayer(layer) and zone.GetNetname() not in ['GND',net]:
                for zi in range(zone.Outline().OutlineCount()):
                    ring=zone.Outline().COutline(zi)
                    sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
                    shapes.append(sh.buffer(clearance));via_obstacles.append(sh.buffer(.505))
            if not zone.GetIsRuleArea() or not zone.IsOnLayer(layer):continue
            for zi in range(zone.Outline().OutlineCount()):
                ring=zone.Outline().COutline(zi)
                sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
                shapes.append(sh.buffer(clearance));via_obstacles.append(sh.buffer(.505))''')
m=types.ModuleType('led_multilayer');exec(compile(multi,'led_multilayer','exec'),m.__dict__)
def route_any(start,end,**kwargs):
    try:return r.route(start,end,layer=p.B_Cu,**kwargs)
    except(RuntimeError,AssertionError):return m.route(r,start,end,**kwargs)
data=json.loads((OUT/'design.json').read_text(encoding='utf-8'));parts={q['ref']:q for q in data['parts']}
fps={fp.GetReference():fp for fp in b.GetFootprints()}
LIB=REPO/'build/cad-tools/kicad/share/kicad/footprints'
def point(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def net(name):
    n=b.FindNet(name)
    if n is None:n=p.NETINFO_ITEM(b,name);b.Add(n)
    return n
rootuuid=re.search(r'\(uuid ([0-9a-f-]+)\)',(OUT/'voice_mainboard_v7.kicad_sch').read_text(encoding='utf-8')).group(1)
UID=lambda name:str(uuid.uuid5(uuid.NAMESPACE_URL,'voice-indicators-20261124/'+name))

# GPIO38 is WROOM pin31 (manufacturer table), not pin34/GPIO41.
# Preserve original route after its first via; remove only the old pad escape.
from shapely.geometry import LineString,box
released_ground=[]
gpio_corridor=box(27.5,16.8,33.5,21)
for t in list(b.GetTracks()):
    if isinstance(t,p.PCB_VIA)or t.GetNetname()!='GND':continue
    sh=LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))])
    if sh.intersects(gpio_corridor):
        released_ground.append(t.m_Uuid.AsString());held.append(t);b.Remove(t)
oldpad=r.pad('U7',34);newpad=r.pad('U7',31);charge='CHG_DISABLE_IO38'
assert oldpad.GetNetname()==charge and parts['U7']['pins']['31']==''
for t in list(b.GetTracks()):
    if isinstance(t,p.PCB_VIA)or t.GetNetname()!='CHG_FULL_N'or t.GetLayer()!=p.F_Cu:continue
    a=(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y));z=(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))
    if abs(a[0]-29.9)<.02 and abs(z[0]-29.9)<.02 and min(a[1],z[1])<18 and max(a[1],z[1])>20:
        held.append(t);b.Remove(t)
        r.direct('CHG_FULL_N',[a,(30.8,a[1]),(30.8,z[1]),z],p.ToMM(t.GetWidth()),p.F_Cu)
tracks=[t for t in b.GetTracks()if t.GetNetname()==charge and not isinstance(t,p.PCB_VIA)]
vias=[t for t in b.GetTracks()if t.GetNetname()==charge and isinstance(t,p.PCB_VIA)]
def key(v):return(v.x,v.y)
at=key(oldpad.GetPosition());endvia=None
for _ in range(25):
    endvia=next((v for v in vias if key(v.GetPosition())==at),None)
    if endvia is not None:break
    connected=[t for t in tracks if at in [key(t.GetStart()),key(t.GetEnd())]and t not in held]
    assert len(connected)==1,('Charge source escape is not a simple chain',at,len(connected))
    t=connected[0];at=key(t.GetEnd())if key(t.GetStart())==at else key(t.GetStart());held.append(t);b.Remove(t)
assert endvia is not None
oldvia_key=key(endvia.GetPosition());newvia_point=point(30.3,p.ToMM(endvia.GetPosition().y))
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA)or t.GetNetname()!=charge:continue
    if key(t.GetStart())==oldvia_key:t.SetStart(newvia_point)
    if key(t.GetEnd())==oldvia_key:t.SetEnd(newvia_point)
endvia.SetPosition(newvia_point)
oldpad.SetNet(net('unconnected-(U7-IO41-Pad34)'));newpad.SetNet(net(charge))
parts['U7']['pins']['34']='';parts['U7']['pins']['31']=charge
parts['U7']['names'].update({'31':['IO38','bidirectional'],'32':['IO39','bidirectional'],'34':['IO41','bidirectional']})
r.virtual['old_charge_via']=endvia
# Reserve the RGB pad exit before routing its neighbouring charger control.
status='STATUS_LED_IO39'
assert parts['U7']['pins']['32']==''
r.pad('U7',32).SetNet(net(status));parts['U7']['pins']['32']=status
p.SaveBoard(str(OUT/'exports/pad-escape-debug.kicad_pcb'),b)
r.escapevia('rgb_gpio_source',('U7',32),diameter=.5,drill=.3,neck=.18)
try:
    r.route(('U7',31),('old_charge_via',0),layer=p.F_Cu,width=.2,step=.05,bounds=(22,12,40,28))
except (RuntimeError,AssertionError):
    r.escapevia('new_charge_via',('U7',31),diameter=.5,drill=.3,neck=.18)
    route_any(('new_charge_via',0),('old_charge_via',0),width=.2,step=.1,bounds=(22,12,55,55))

# New GPIO39 uses manufacturer WROOM pin32; not N8R8 PSRAM pins28..30.

newparts=[
 {'ref':'D2','value':'WS2812B-2020-V6','footprint':'LED_SMD:LED_WS2812B-2020_PLCC4_2.0x2.0mm','pins':{'1':'','2':'GND','3':'RGB_LED_DIN','4':'ESP_3V3'}},
 {'ref':'R77','value':'330R RGB DIN','footprint':'Resistor_SMD:R_0603_1608Metric','pins':{'1':status,'2':'RGB_LED_DIN'}},
 {'ref':'C74','value':'100n RGB','footprint':'Capacitor_SMD:C_0603_1608Metric','pins':{'1':'ESP_3V3','2':'GND'}},
]
from shapely.geometry import Point,LineString,Polygon,box
from shapely.ops import unary_union
# Find free placement along left side while respecting copper and courtyards.
shapes=[]
for fp in b.GetFootprints():
    for pd in fp.Pads():
        if pd.IsOnLayer(p.F_Cu):shapes.extend(sh.buffer(.205)for sh in r.polygons(pd,p.F_Cu))
    courts=[gi.GetBoundingBox()for gi in fp.GraphicalItems()if gi.GetLayer()==p.F_CrtYd]
    if courts:
        shapes.append(box(min(p.ToMM(bb.GetLeft())for bb in courts),min(p.ToMM(bb.GetTop())for bb in courts),max(p.ToMM(bb.GetRight())for bb in courts),max(p.ToMM(bb.GetBottom())for bb in courts)))
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):shapes.append(Point(r.pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2+.205))
    elif t.GetLayer()==p.F_Cu:shapes.append(LineString([r.pos(t), (p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2+.205))
for zone in [*b.Zones(),*[z for fp in b.GetFootprints()for z in fp.Zones()]]:
    if not zone.GetIsRuleArea() and zone.GetNetname()!='GND':
        for zi in range(zone.Outline().OutlineCount()):
            ring=zone.Outline().COutline(zi);shapes.append(Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]).buffer(.205))
    if not zone.GetIsRuleArea()or not zone.IsOnLayer(p.F_Cu):continue
    for zi in range(zone.Outline().OutlineCount()):
        ring=zone.Outline().COutline(zi);shapes.append(Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]))
blocked=unary_union(shapes)
placement=None
candidate_anchors=sorted([(float(x),float(y))for y in range(3,68)for x in range(3,94)],key=lambda q:(q[0]-28.75)**2+(q[1]+2-17.9)**2)
for x,y in candidate_anchors:
        areas=[box(x-1.6,y-1.3,x+1.6,y+1.3),box(x+2.55,y-1,x+5.45,y+1),box(x-1.45,y+2,x+1.45,y+4)]
        if not any(blocked.intersects(a)for a in areas):placement=(x,y);break
assert placement,'No free indicator pair placement in the searched left-side region'
x,y=placement
print('RGB placement',placement,flush=True)
positions={'D2':(x,y),'R77':(x+4,y),'C74':(x,y+3)}
for q in newparts:
    lib,name=q['footprint'].split(':');f=p.FootprintLoad(str(LIB/(lib+'.pretty')),name);assert f
    f.SetReference(q['ref']);f.SetValue(q['value']);f.Value().SetVisible(False);f.Reference().SetVisible(False)
    f.SetFPID(p.LIB_ID(lib,name))
    if q['ref']=='D2':f.SetOrientationDegrees(180)
    f.SetPosition(point(*positions[q['ref']]));b.Add(f);fps[q['ref']]=f
    for pd in f.Pads():pd.SetNet(net(q['pins'][pd.GetNumber()]))if q['pins'].get(pd.GetNumber())else pd.SetNet(net('unconnected-(D2-DO-Pad1)'))
    f.SetPath(p.KIID_PATH('/'+rootuuid+'/'+UID('symbol/'+q['ref'])))
    q.update(x=positions[q['ref']][0],y=positions[q['ref']][1],angle=180 if q['ref']=='D2'else 0,names={},group='05 ESP / BOOT / ADC / TTL',dnp=False,kind='pcb',side='F',lcsc='C52917434'if q['ref']=='D2'else None,mpn=q['value']if q['ref']=='D2'else None,source='https://item.szlcsc.com/55827425.html'if q['ref']=='D2'else'',note='RGB V6 pin1 DO,2 GND,3 DI,4 VDD. Standard footprint rotated180 to match manufacturer top-view; actual supply corner and physical fit need qualification.',price_basis='RGB public1000 tier0.3198; passives allowance not final JLC price')
    if q['ref']=='D2':q['names']={'1':['DO','output'],'2':['GND','power_in'],'3':['DI','input'],'4':['VDD','power_in']}
    data['parts'].append(q);parts[q['ref']]=q

r.route(('R77',2),('D2',3),width=.2,step=.05,bounds=(x-2,y-2,x+7,y+6))
r.route(('C74',1),('D2',4),width=.2,step=.05,bounds=(x-2,y-2,x+7,y+6))
r.virtual['LED_ESP_SOURCE']=min([pd for fp in b.GetFootprints()for pd in fp.Pads()if pd.GetNetname()=='ESP_3V3'and fp.GetReference()not in ['D2','C74']],key=lambda pd:((r.pos(pd)[0]-x)**2+(r.pos(pd)[1]-y)**2))
# All input pad exits remain conventional; optional R31 stays DNP.
for label,start,end in [('status_supply',('D2',4),('LED_ESP_SOURCE',0)),('status_gpio',('R77',1),('U7',32))]:
    r.escapevia(label+'_a',start)
    if label=='status_gpio':target=('rgb_gpio_source',0)
    else:r.escapevia(label+'_z',end);target=(label+'_z',0)
    route_any((label+'_a',0),target,width=.2,step=.1,bounds=(1,1,98,73.4))
r.escapevia('rgb_led_ground',('D2',2));r.escapevia('rgb_cap_ground',('C74',2))
for label,yy in [('RGB',y)]:
    text=p.PCB_TEXT(b);text.SetText(label);text.SetPosition(point(x-1,yy-1.8));text.SetTextSize(point(.8,.8));text.SetTextThickness(p.FromMM(.13));text.SetLayer(p.F_SilkS);b.Add(text)

# Incremental schematic writer: top-level S-expression spans without a lossy
# parser/reformatter. Only U7 pin connections + new symbols are added.
def spans(text):
    result=[];depth=0;quoted=False;escape=False;start=None
    for i,c in enumerate(text):
        if quoted:
            if escape:escape=False
            elif c=='\\':escape=True
            elif c=='"':quoted=False
            continue
        if c=='"':quoted=True
        elif c=='(':
            if depth==1:start=i
            depth+=1
        elif c==')':
            depth-=1
            if depth==1 and start is not None:result.append((start,i+1));start=None
    return result
Q=lambda s:json.dumps(str(s),ensure_ascii=False)
sch=(OUT/'voice_mainboard_v7.kicad_sch').read_text(encoding='utf-8')
# Correct affected pin names in embedded/library symbols, while preserving
# all existing symbol UUIDs and pin numbers.
def correct_u7_names(text):
    return re.sub(r'(\(pin [^\n]*?\(name ")[^"]*("[^\n]*?\(number "(31|32|34)")',lambda m:m.group(1)+{'31':'IO38','32':'IO39','34':'IO41'}[m.group(3)]+m.group(2),text)
lib_container=next(sch[a:z]for a,z in spans(sch)if sch[a:z].startswith('(lib_symbols'))
embedded_u7=next(lib_container[a:z]for a,z in spans(lib_container)if lib_container[a:z].startswith('(symbol "VoiceV2:U7"'))
lib_start=sch.index(embedded_u7);lib_end=lib_start+len(embedded_u7)
sch=sch[:lib_start]+correct_u7_names(sch[lib_start:lib_end])+sch[lib_end:]
u7span=next((a,z)for a,z in spans(sch)if sch[a:z].startswith('(symbol (lib_id "VoiceV2:U7")'))
u7=sch[u7span[0]:u7span[1]];xc,yc=map(float,re.search(r'\(at ([0-9.]+) ([0-9.]+) 0\)',u7).groups())
symbolspan=next((a,z)for a,z in spans(sch)if sch[a:z].startswith('(lib_symbols'))
libtext=sch[symbolspan[0]:symbolspan[1]]
libu7=re.search(r'\(symbol "VoiceV2:U7"(.*?)\n\)\)',libtext,re.S).group(0)
edits=[];links=[]
for number,newnet in [('31',charge),('32',status),('34','')]:
    # Coordinates use the existing embedded pin rather than assuming row order.
    match=re.search(r'\(pin [^\n]*?\(at ([\-0-9.]+) ([\-0-9.]+) ([0-9]+)\)[^\n]*?\(number "'+number+r'"',libu7)
    assert match,number
    px,py,ang=map(float,match.groups());gx=round(xc+px,6);gy=round(yc-py,6);ex=round(gx+(-5.08 if ang==0 else 5.08),6)
    for a,z in spans(sch):
        chunk=sch[a:z]
        if chunk.startswith('(no_connect')and re.search(r'\(at '+str(gx)+r' '+str(gy)+r'\)',chunk):edits.append((a,z,''))
        if chunk.startswith('(wire')and f'(xy {gx} {gy})'in chunk:edits.append((a,z,''))
        if chunk.startswith('(global_label')and re.search(r'\(at '+str(ex)+r' '+str(gy)+r' ',chunk):edits.append((a,z,''))
    if newnet:
        links.append(f'(wire (pts (xy {gx} {gy}) (xy {ex} {gy})) (stroke (width 0) (type default)) (uuid {UID("wire/U7/"+number)}))')
        links.append(f'(global_label {Q(newnet)} (shape input) (at {ex} {gy} {int(ang)}) (effects (font (size .95 .95)) (justify {"left"if ang==0 else"right"} bottom)) (uuid {UID("label/U7/"+number)}))')
    else:links.append(f'(no_connect (at {gx} {gy}) (uuid {UID("nc/U7/"+number)}))')
libdefs=[];instances=[]
for index,q in enumerate(newparts):
    ref=q['ref'];sx,sy=round(1080/1.27)*1.27,round((260+index*26)/1.27)*1.27
    pin_y={num:round((len(q['pins'])-1-2*i)*1.27,6)for i,num in enumerate(q['pins'])}
    pindefs=[]
    for num,py in pin_y.items():
        name,kind=q['names'].get(num,[num,'passive'])
        pindefs.append(f'(pin {kind} line (at -7.62 {py} 0) (length 2.54) (name {Q(name)} (effects (font (size 1 1)))) (number {Q(num)} (effects (font (size 1 1)))))')
    ss=f'''(symbol "VoiceV2:{ref}" (pin_names (offset .5)) (in_bom yes) (on_board yes)
      (property "Reference" "{ref}" (at 0 5 0) (effects (font (size 1.27 1.27))))
      (property "Value" {Q(q['value'])} (at 0 -5 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" {Q(q['footprint'])} (at 0 0 0) (effects (font (size 1 1)) hide))
      (symbol "{ref}_0_1" (rectangle (start -5.08 5.08) (end 5.08 -5.08) (stroke (width .254) (type default)) (fill (type background))))
      (symbol "{ref}_1_1" {' '.join(pindefs)}))'''
    libdefs.append(ss)
    instances.append(f'''(symbol (lib_id "VoiceV2:{ref}") (at {sx} {sy} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {UID('symbol/'+ref)})
     (property "Reference" "{ref}" (at {sx} {sy-6} 0) (effects (font (size 1.27 1.27))))
     (property "Value" {Q(q['value'])} (at {sx} {sy+6} 0) (effects (font (size 1 1))))
     (property "Footprint" {Q(q['footprint'])} (at {sx} {sy} 0) (effects (font (size 1 1)) hide))
     {' '.join(f'(pin "{num}" (uuid {UID("pin/"+ref+"/"+num)}))'for num in q['pins'])}
     (instances (project "voice_mainboard_v7" (path "/{rootuuid}" (reference "{ref}") (unit 1)))))''')
    for num,py in pin_y.items():
        gx,gy=round(sx-7.62,6),round(sy-py,6);ex=round(gx-5.08,6)
        if not q['pins'][num]:
            links.append(f'(no_connect (at {gx} {gy}) (uuid {UID("nc/"+ref+"/"+num)}))');continue
        links.append(f'(wire (pts (xy {gx} {gy}) (xy {ex} {gy})) (stroke (width 0) (type default)) (uuid {UID("wire/"+ref+"/"+num)}))')
        links.append(f'(global_label {Q(q["pins"][num])} (shape input) (at {ex} {gy} 0) (effects (font (size 1 1)) (justify left bottom)) (uuid {UID("label/"+ref+"/"+num)}))')
edits.append((symbolspan[1]-1,symbolspan[1]-1,'\n'+'\n'.join(libdefs)+'\n'))
for a,z,new in sorted(edits,reverse=True):sch=sch[:a]+new+sch[z:]
sch=sch.rstrip()[:-1]+'\n'+'\n'.join(instances+links)+'\n)\n'
(OUT/'voice_mainboard_v7.kicad_sch').write_text(sch,encoding='utf-8')
symbols=(OUT/'VoiceV2.kicad_sym').read_text(encoding='utf-8').rstrip()
library_u7=next(symbols[a:z]for a,z in spans(symbols)if symbols[a:z].startswith('(symbol "U7"'))
lib_start=symbols.index(library_u7);lib_end=lib_start+len(library_u7)
symbols=symbols[:lib_start]+correct_u7_names(symbols[lib_start:lib_end])+symbols[lib_end:]
(OUT/'VoiceV2.kicad_sym').write_text(symbols[:-1]+'\n'+'\n'.join(s.replace('(symbol "VoiceV2:','(symbol "')for s in libdefs)+'\n)\n',encoding='utf-8')
data['revision']='V7-RGB-CANDIDATE-20261124';data['gpio_contract']['rgb_led_data']=39
data['indicators']={'rgb':{'ref':'D2','model':'WS2812B-2020-V6','GPIO':39,'module_pad':32,'rail':'ESP_3V3','pins':{'1':'DO NC','2':'GND','3':'DI','4':'VDD'},'firmware_implemented':False,'power_indicator_independent':False},'charger_GPIO38_pad_corrected':31}
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
(OUT/'exports/indicator-changes.json').write_text(json.dumps({'base_sha256':hashlib.sha256((BASE/FILE.name).read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'new_refs':[q['ref']for q in newparts],'placement_mm':positions,'status_GPIO':39,'status_module_pad':32,'charger_correction':{'old_module_pad':34,'old_actual_GPIO':41,'correct_module_pad':31,'correct_GPIO':38},'manufacturing_ready':False,'firmware_implemented':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Created LED candidate',positions,flush=True)
