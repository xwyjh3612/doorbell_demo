"""Local SIM/strap refinement; preserve BOM, real pads and routed power.

The SIM ESD and series resistors move behind the socket. Boot pull-up moves
beside ESP GPIO0, and input gate pull-down moves beside its FET. Check actual
SIM pegs, courtyard/pad collisions and then reroute the affected connections.
"""
from pathlib import Path
import datetime, json, math, shutil, sys
import pcbnew as p
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'build/cad-tools/route-python'))
from shapely.geometry import Point,LineString,Polygon,box
from shapely.ops import polygonize,unary_union
OUT=ROOT/'two_layer_work';FILE=OUT/'voice_mainboard_a18_2layer.kicad_pcb'
snap=OUT/'iterations'/('before-sim-strap-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));snap.mkdir(parents=True)
for name in [FILE.name,'design.json']:shutil.copy2(OUT/name,snap/name)
b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()}
data=json.loads((OUT/'design.json').read_text(encoding='utf-8'))
def xy(v):return p.ToMM(v.x),p.ToMM(v.y)
def copper(d,layer):
    sh=d.GetEffectivePolygon(layer)
    return unary_union([Polygon([xy(q.CPoint(j)) for j in range(q.PointCount())]) for q in [sh.COutline(i) for i in range(sh.OutlineCount())] if q.PointCount()>=3])
def court(f):
    lines=[];circles=[]
    for g in f.GraphicalItems():
        if g.GetLayer() not in [p.F_CrtYd,p.B_CrtYd]:continue
        if g.GetShape()==p.S_SEGMENT:lines.append(LineString([xy(g.GetStart()),xy(g.GetEnd())]))
        elif g.GetShape()==p.S_CIRCLE:circles.append(Point(xy(g.GetStart())).buffer(math.dist(xy(g.GetStart()),xy(g.GetEnd()))))
    return unary_union([*polygonize(lines),*circles])
targets={'D1':(35.5,21,270,'B'),'R9':(40.5,21,90,'B'),'R10':(40.5,18,90,'B'),
         'R11':(40.5,24,90,'B'),'C20':(35.5,24.5,0,'B'),
         'R14':(28.75,26.5,0,'B'),'R32':(58.5,39.5,0,'B')}
before=sorted((f.GetReference(),d.GetNumber(),d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
reset={'M_SIM_DATA','M_SIM_CLK','M_SIM_RESET','SIM_DATA','SIM_CLK','SIM_RESET','SIM_VCC','CALL_BOOT0','REVERSE_GATE'}
oldpads=[d.GetPosition() for ref in targets for d in fps[ref].Pads()]
oldpoints={(q.x,q.y) for q in oldpads};held=[];removed=[]
for t in list(b.GetTracks()):
    incident=not isinstance(t,p.PCB_VIA) and any((q.x,q.y) in oldpoints for q in [t.GetStart(),t.GetEnd()])
    if t.GetNetname() in reset or incident:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'incident_only':incident and t.GetNetname() not in reset})
        held.append(t);b.Remove(t)
placed=set(fps)-set(targets);outline=Polygon(data['mechanical']['outline_mm']).buffer(-.5)
entries=[]
for ref,(tx,ty,angle,side) in targets.items():
    f=fps[ref];layer=p.B_Cu if side=='B' else p.F_Cu
    if f.GetLayer()!=layer:f.Flip(f.GetPosition(),False)
    f.SetOrientationDegrees(angle)
    occupied=unary_union([court(fps[r]).buffer(.08) for r in placed if fps[r].GetLayer()==layer])
    peg_keepouts=unary_union([Point(xy(d.GetPosition())).buffer(max(xy(d.GetDrillSize()))/2+.4) for r in placed for d in fps[r].Pads() if d.GetAttribute()==p.PAD_ATTRIB_NPTH and d.GetDrillSize().x])
    pad_obstacles=[(d.GetNetname(),copper(d,layer)) for r in placed for d in fps[r].Pads() if d.IsOnLayer(layer)]
    track_obstacles=[]
    for t in b.GetTracks():
        if not t.IsOnLayer(layer):continue
        shape=Point(xy(t.GetPosition())).buffer(p.ToMM(t.GetWidth(layer))/2) if isinstance(t,p.PCB_VIA) else LineString([xy(t.GetStart()),xy(t.GetEnd())]).buffer(p.ToMM(t.GetWidth())/2)
        track_obstacles.append((t.GetNetname(),shape))
    found=None
    for x,y in sorted(((tx+dx*.25,ty+dy*.25) for dx in range(-16,17) for dy in range(-16,17)),key=lambda q:math.dist(q,(tx,ty))):
        f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));sh=court(f)
        if not outline.covers(sh) or occupied.intersects(sh) or peg_keepouts.intersects(sh):continue
        good=True
        for d in f.Pads():
            own=copper(d,layer)
            for net,shape in pad_obstacles:
                if net!=d.GetNetname() and own.distance(shape)<.201:good=False;break
            if not good:break
            for net,shape in track_obstacles:
                if net==d.GetNetname():continue
                if own.distance(shape)<.201:good=False;break
            if not good:break
        if good:found=(x,y);break
    if found is None:
        for item in held:item.thisown=False
        raise RuntimeError('No local placement for '+ref+'; saved board not overwritten')
    placed.add(ref);entries.append({'ref':ref,'target':[tx,ty],'actual_mm':found,'side':side,'angle':angle})
assert before==sorted((f.GetReference(),d.GetNumber(),d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
for q in data['parts']:
    f=fps[q['ref']];q.update(x=xy(f.GetPosition())[0],y=xy(f.GetPosition())[1],angle=f.GetOrientationDegrees(),side='B' if f.GetLayer()==p.B_Cu else 'F')
data.setdefault('two_layer_iterations',[]).append({'snapshot':str(snap.relative_to(OUT)),'reason':'SIM ESD/series components beside socket, GPIO0 pull-up beside ESP, reverse gate resistor beside FET','moves':entries})
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(OUT/'exports/sim-strap-relocation.json').write_text(json.dumps({'moves':entries,'removed_routes':removed,'native_DRC_required':True},indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Moved SIM/strap components with unchanged pads and BOM:',entries,flush=True)
