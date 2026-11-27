"""Add the manufacturer's two VBAT storage capacitors without changing MLCCs.

Place the body and lands against actual same-side courtyards and copper. Native
ERC, parity and DRC remain mandatory. The standard land pattern still needs a
physical sample check; the APAQ series drawing specifies the lead envelope.
"""
import datetime
import json
import math
import re
import shutil
import uuid
from pathlib import Path

from comparison_route_geometry import b, FILE, p, pos, polys, outline, required_clearance
from route_net_classes import PROTECTED
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

OUT = FILE.parent
SOURCE = Path(__file__).resolve().parent
REPO = SOURCE.parents[1]
SCHEMATIC = FILE.with_suffix('.kicad_sch')
data = json.loads((OUT/'design.json').read_text(encoding='utf-8'))
assert not {'C75', 'C76'}.intersection(q['ref'] for q in data['parts'])
snapshot = OUT/'iterations'/('before-vbat-storage-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
for f in [FILE, SCHEMATIC, OUT/'design.json']:
    shutil.copy2(f, snapshot/f.name)

def court(fp):
    lines, shapes = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() not in [p.F_CrtYd, p.B_CrtYd]: continue
        if g.GetShape() == p.S_SEGMENT:
            a,z=g.GetStart(),g.GetEnd()
            lines.append(LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]))
        elif g.GetShape() == p.S_RECT:
            a,z=g.GetStart(),g.GetEnd()
            shapes.append(box(min(p.ToMM(a.x),p.ToMM(z.x)),min(p.ToMM(a.y),p.ToMM(z.y)),max(p.ToMM(a.x),p.ToMM(z.x)),max(p.ToMM(a.y),p.ToMM(z.y))))
        elif g.GetShape() == p.S_CIRCLE:
            a,z=g.GetStart(),g.GetEnd()
            shapes.append(Point(p.ToMM(a.x),p.ToMM(a.y)).buffer(math.hypot(p.ToMM(a.x-z.x),p.ToMM(a.y-z.y))))
        elif g.GetShape() == p.S_POLYGON:
            sh=g.GetPolyShape()
            for i in range(sh.OutlineCount()):
                q=sh.COutline(i)
                shapes.append(Polygon([(p.ToMM(q.CPoint(j).x),p.ToMM(q.CPoint(j).y)) for j in range(q.PointCount())]))
    return unary_union([*polygonize(lines),*shapes])

def spans(text):
    result=[]; depth=0; quoted=False; escaped=False; start=None
    for i,ch in enumerate(text):
        if quoted:
            if escaped: escaped=False
            elif ch=='\\': escaped=True
            elif ch=='"': quoted=False
            continue
        if ch=='"': quoted=True
        elif ch=='(':
            if depth==1: start=i
            depth+=1
        elif ch==')':
            depth-=1
            if depth==1 and start is not None: result.append((start,i+1)); start=None
    return result

UID=lambda name:str(uuid.uuid5(uuid.NAMESPACE_URL,'voice-a18-vbat-storage/'+name))
Q=lambda s:json.dumps(str(s),ensure_ascii=False)
text=SCHEMATIC.read_text(encoding='utf-8')
rootuuid=re.search(r'\(uuid ([0-9a-f-]+)\)',text)[1]
libspan=next((a,z) for a,z in spans(text) if text[a:z].startswith('(lib_symbols'))
library=[]; instances=[]; links=[]; added=[]; held=[]; retired=[]
for index,ref in enumerate(['C75','C76']):
    fp=p.FootprintLoad(str(REPO/'build/cad-tools/kicad/share/kicad/footprints/Capacitor_SMD.pretty'),'CP_Elec_6.3x4.5')
    fp.SetReference(ref); fp.SetValue('220u 6.3V APAQ6R3AVEA221M0645')
    fp.Value().SetVisible(False)
    fp.SetFPID(p.LIB_ID('Capacitor_SMD','CP_Elec_6.3x4.5'))
    fp.SetPath(p.KIID_PATH('/'+rootuuid+'/'+UID('symbol/'+ref)))
    b.Add(fp)
    fp.Flip(fp.GetPosition(),False)
    for d in fp.Pads(): d.SetNet(b.FindNet('MODEM_3V8' if d.GetNumber()=='1' else 'GND'))
    peers=[f for f in b.GetFootprints() if f!=fp]
    occupied=unary_union([court(f).buffer(.08) for f in peers if f.GetLayer()==p.B_Cu])
    obstacles=[]
    for f in peers:
        for d in f.Pads():
            if d.IsOnLayer(p.B_Cu): obstacles.extend((d.GetNetname(),sh,None) for sh in polys(d,p.B_Cu))
    for t in b.GetTracks():
        if not t.IsOnLayer(p.B_Cu): continue
        if isinstance(t,p.PCB_VIA): sh=Point(pos(t)).buffer(p.ToMM(t.GetWidth(p.B_Cu))/2)
        else:
            a,z=t.GetStart(),t.GetEnd()
            sh=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]).buffer(p.ToMM(t.GetWidth())/2)
        obstacles.append((t.GetNetname(),sh,t))
    obstacle_tree=STRtree([q[1] for q in obstacles])
    candidates=[]
    for angle in [0,90,180,270]:
        fp.SetOrientationDegrees(angle)
        for ix in range(172,237):
            for iy in range(48,137):
                xy=(ix*.25,iy*.25)
                fp.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
                sh=court(fp)
                if occupied.intersects(sh) or not outline.buffer(-.5).covers(sh): continue
                hits=[]; blocked=False
                for d in fp.Pads():
                    for own in polys(d,p.B_Cu):
                        for obstacle_index in obstacle_tree.query(own.buffer(.202)):
                            net,shape,obj=obstacles[int(obstacle_index)]
                            if own.distance(shape) >= required_clearance(d.GetNetname(),net): continue
                            if isinstance(obj,p.PCB_VIA) and own.distance(shape)<.05:
                                blocked=True; break
                            if d.GetNetname()==net: continue
                            if obj is None or obj.IsLocked() or net in PROTECTED:
                                blocked=True;break
                            hits.append(obj)
                        if blocked: break
                    if blocked: break
                if not blocked:
                    positive=next(d for d in fp.Pads() if d.GetNumber()=='1')
                    score=math.dist(pos(positive),(51.2,16.55)) + 1.5*len(hits)
                    candidates.append((score,xy,angle,hits))
    assert candidates, 'No body/land-safe placement for '+ref
    score,xy,angle,hits=min(candidates,key=lambda q:q[0])
    fp.SetOrientationDegrees(angle)
    fp.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
    for t in {q.m_Uuid.AsString():q for q in hits}.values():
        retired.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()}); b.Remove(t);held.append(t)
    part={'ref':ref,'value':fp.GetValue(),'footprint':'Capacitor_SMD:CP_Elec_6.3x4.5','pins':{'1':'MODEM_3V8','2':'GND'},'names':{'1':['+','passive'],'2':['-','passive']},'x':xy[0],'y':xy[1],'angle':angle,'side':'B','dnp':False,'kind':'pcb','group':'01 EXTERNAL INPUT / PRIMARY 3.8V','mpn':'6R3AVEA221M0645','lcsc':'C176322','source':'https://item.szlcsc.com/187712.html','note':'APAQ AVEA 0645: 220uF +/-20%,6.3V,17mOhm ESR at100-300kHz,2.3Arms ripple105C,body6.3x4.3mm. Standard6.3x4.5 land pads3.5x1.6 at+/-2.7mm; verify sample land/polarity before assembly. ML307C hardware AT manual page24 requires at least two220uF on VBAT; retain C6/C7 MLCCs.','price_basis':'Public stock checked20261126; quantity tier quotation pending'}
    data['parts'].append(part); added.append(part)
    sx,sy=1079.5,round((370+index*26)/1.27)*1.27
    pindefs=' '.join(f'(pin passive line (at -7.62 {py} 0) (length 2.54) (name "{name}" (effects (font (size 1 1)))) (number "{num}" (effects (font (size 1 1)))))' for num,py,name in [('1',1.27,'+'),('2',-1.27,'-')])
    library.append(f'''(symbol "VoiceV2:{ref}" (pin_names (offset .5)) (in_bom yes) (on_board yes)
      (property "Reference" "{ref}" (at 0 5 0) (effects (font (size 1.27 1.27))))
      (property "Value" {Q(part['value'])} (at 0 -5 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" {Q(part['footprint'])} (at 0 0 0) (effects (font (size 1 1)) hide))
      (symbol "{ref}_0_1" (rectangle (start -5.08 5.08) (end 5.08 -5.08) (stroke (width .254) (type default)) (fill (type background))))
      (symbol "{ref}_1_1" {pindefs}))''')
    instances.append(f'''(symbol (lib_id "VoiceV2:{ref}") (at {sx} {sy} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {UID('symbol/'+ref)})
      (property "Reference" "{ref}" (at {sx} {sy-6} 0) (effects (font (size 1.27 1.27))))
      (property "Value" {Q(part['value'])} (at {sx} {sy+6} 0) (effects (font (size 1 1))))
      (property "Footprint" {Q(part['footprint'])} (at {sx} {sy} 0) (effects (font (size 1 1)) hide))
      (pin "1" (uuid {UID('pin/'+ref+'/1')})) (pin "2" (uuid {UID('pin/'+ref+'/2')}))
      (instances (project "voice_mainboard_a18_2layer" (path "/{rootuuid}" (reference "{ref}") (unit 1)))))''')
    for num,py in [('1',1.27),('2',-1.27)]:
        gx,gy=round(sx-7.62,6),round(sy-py,6);ex=round(gx-5.08,6)
        links.append(f'(wire (pts (xy {gx} {gy}) (xy {ex} {gy})) (stroke (width 0) (type default)) (uuid {UID("wire/"+ref+"/"+num)}))')
        links.append(f'(global_label {Q(part["pins"][num])} (shape input) (at {ex} {gy} 0) (effects (font (size 1 1)) (justify left bottom)) (uuid {UID("label/"+ref+"/"+num)}))')

text=text[:libspan[1]-1]+'\n'+'\n'.join(library)+'\n'+text[libspan[1]-1:]
text=text.rstrip()[:-1]+'\n'+'\n'.join(instances+links)+'\n)\n'
SCHEMATIC.write_text(text,encoding='utf-8')
libfile=SOURCE/'VoiceV2.kicad_sym'
libtext=libfile.read_text(encoding='utf-8').rstrip()
libfile.write_text(libtext[:-1]+'\n'+'\n'.join(s.replace('(symbol "VoiceV2:','(symbol "') for s in library)+'\n)\n',encoding='utf-8')
data['two_layer_iterations'].append({'snapshot':str(snapshot.relative_to(OUT)),'reason':'Manufacturer-required two220uF ML307C VBAT storage capacitors','added_refs':['C75','C76']})
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity(); assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
(OUT/'exports/modem-vbat-storage.json').write_text(json.dumps({'parts':added,'retired_ordinary_signal_copper':retired,'preserved_MLCC':['C6','C7'],'manufacturer_source':'../sources/ml307c-at-hardware.txt page24','native_revalidation_required':True,'sample_land_check_pending':True},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'placed':[{k:q[k] for k in ['ref','x','y','angle']} for q in added],'retired_signals':len(retired)},indent=2))
