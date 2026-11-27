"""Face the boost switch pins toward the inductor and shorten feedback.

Same ETA1096, inductor and capacitor values. Preserve the routed main supply
outside the changed local loop; recheck all changed connections natively.
"""
from pathlib import Path
import datetime,json,shutil,sys
import pcbnew as p
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'two_layer_work';FILE=OUT/'voice_mainboard_a18_2layer.kicad_pcb'
sys.path.insert(0,str(ROOT.parents[1]/'build/cad-tools/route-python'))
from shapely.geometry import Point,Polygon,LineString,box
snap=OUT/'iterations'/('before-boost-loop-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));snap.mkdir(parents=True)
for name in [FILE.name,'design.json']:shutil.copy2(OUT/name,snap/name)
b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()};data=json.loads((OUT/'design.json').read_text(encoding='utf-8'))
contract=lambda:sorted((f.GetReference(),d.GetNumber(),d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
before=contract()
moves={'U15':(30,48,270),'R61':(34.25,49.75,180),'R62':(34.25,48,0),
       'R63':(33.5,52.25,270),'C64':(18.75,46,180),'C65':(30,53,0),
       'C66':(36.25,52,0),'R28':(31.5,44.75,0),'R29':(33.5,44.75,0)}
oldpoints={(d.GetPosition().x,d.GetPosition().y) for ref in moves for d in fps[ref].Pads()}
reset={'UPS_SW','UPS_FB','UPS_ISET','BOOST_EN'};held=[];removed=[]
for t in list(b.GetTracks()):
    incident=not isinstance(t,p.PCB_VIA) and any((q.x,q.y) in oldpoints for q in [t.GetStart(),t.GetEnd()])
    # The old VOUT escape via occupied the new short switch route.
    old_boost_escape=isinstance(t,p.PCB_VIA) and t.GetNetname()=='BAT_BOOST_5V' and box(25.5,42.8,31.5,46.0).contains(Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y)))
    if t.GetNetname() in reset or incident or old_boost_escape:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'reason':'reset-local-net' if t.GetNetname() in reset else 'moved-pad/old-escape'})
        held.append(t);b.Remove(t)
for ref,(x,y,a) in moves.items():fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));fps[ref].SetOrientationDegrees(a)

# A new SMT pad must not inadvertently become an unfilled via-in-pad.
def shape(d,layer):
    sh=d.GetEffectivePolygon(layer)
    return [Polygon([(p.ToMM(q.CPoint(j).x),p.ToMM(q.CPoint(j).y)) for j in range(q.PointCount())]) for q in [sh.COutline(i) for i in range(sh.OutlineCount())] if q.PointCount()>=3]
for t in list(b.GetTracks()):
    if not isinstance(t,p.PCB_VIA):continue
    point=Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y));radius=p.ToMM(t.GetWidth(p.F_Cu))/2
    hit=False
    for ref in moves:
        for d in fps[ref].Pads():
            if d.GetAttribute()!=p.PAD_ATTRIB_SMD:continue
            margin=.05 if d.GetNetname()==t.GetNetname() else .201
            if any(sh.distance(point)<radius+margin for sh in shape(d,fps[ref].GetLayer())):hit=True;break
        if hit:break
    if hit:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'reason':'off-pad-via-clearance-at-moved-SMT-pad'});held.append(t);b.Remove(t)
assert contract()==before
for q in data['parts']:
    f=fps[q['ref']];q.update(x=p.ToMM(f.GetPosition().x),y=p.ToMM(f.GetPosition().y),angle=f.GetOrientationDegrees(),side='B' if f.GetLayer()==p.B_Cu else 'F')
data.setdefault('two_layer_iterations',[]).append({'snapshot':str(snap.relative_to(OUT)),
    'reason':'Boost switch faces inductor; input cap beside inductor input, output cap beside VOUT; feedback/current setting near controller; host straps away from switch route', 'moves':moves})
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(OUT/'exports/boost-loop-refinement.json').write_text(json.dumps({'moves':moves,'removed_routes':removed,'switch_loop_qualified':False},indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Refined boost placement with unchanged pad/net contract and component values.')
