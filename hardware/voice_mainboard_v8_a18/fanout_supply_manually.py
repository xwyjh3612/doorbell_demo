"""Stagger the selector power vias and move boost pins clear of button keepout.

Explicit doglegs replace mutually destructive straight-line pin escapes.
Native DRC, supply estimates and ground checks remain mandatory afterwards.
"""
from pathlib import Path
import json,os,sys
import pcbnew as p
SOURCE=Path(__file__).resolve().parent;sys.path.insert(0,str(SOURCE.parents[1]/'build/cad-tools/route-python'))
from shapely.geometry import LineString,Point,box
FILE=Path(os.environ['A18_REPAIR_BOARD']);ROOT=FILE.parent;b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()}
design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'));parts={q['ref']:q for q in design['parts']}
moves={'U15':(30,48),'C66':(35,52),'R72':(58.5,37),'TP12':(57,33)}
reset={d.GetNetname()for ref in ['U15','C66']for d in fps[ref].Pads()if d.GetNetname()!='GND'}
oldr72={str((d.GetPosition().x,d.GetPosition().y))for d in fps['R72'].Pads()}
held=[];removed=[]
for t in list(b.GetTracks()):
    hit=False
    if t.GetNetname()in reset:hit=True
    elif not isinstance(t,p.PCB_VIA)and any(str((pt.x,pt.y))in oldr72 for pt in [t.GetStart(),t.GetEnd()]):hit=True
    elif t.GetNetname()in ['SYS_5V','VIN_PROTECTED','UPS_PR1','SUPPLY_BAT_N47','GND']:
        if isinstance(t,p.PCB_VIA):shape=Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2)
        else:
            a,z=t.GetStart(),t.GetEnd();shape=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]).buffer(p.ToMM(t.GetWidth())/2)
        hit=shape.intersects(box(63.2,37.7,69.2,42.0))
    if hit:removed.append({'uuid':str(t.m_Uuid.AsString()),'net':t.GetNetname()});held.append(t);b.Remove(t)
for ref,(x,y)in moves.items():fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));parts[ref].update(x=x,y=y)
def add(ref,num,points,diameter=.9,drill=.3,width=.25):
    f=fps[ref];d=next(d for d in f.Pads()if d.GetNumber()==str(num));path=[(p.ToMM(d.GetPosition().x),p.ToMM(d.GetPosition().y)),*points]
    for a,z in zip(path,path[1:]):
        t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])));t.SetEnd(p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1])));t.SetLayer(f.GetLayer());t.SetWidth(p.FromMM(width));t.SetNetCode(d.GetNetCode());t.SetLocked(True);b.Add(t)
    if diameter:
        v=p.PCB_VIA(b);v.SetPosition(p.VECTOR2I(p.FromMM(path[-1][0]),p.FromMM(path[-1][1])));v.SetWidth(p.FromMM(diameter));v.SetDrill(p.FromMM(drill));v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNetCode(d.GetNetCode());v.SetLocked(True);b.Add(v)
    return {'pad':[ref,str(num)],'net':d.GetNetname(),'path_mm':path,'via_diameter_mm':diameter,'neck_width_mm':width}
fanouts=[
    add('U18',3,[(64.6,39.75),(64.05,40.3),(64,40.3)]),
    add('U18',2,[(66.74,40.25)],0,0),
    add('U18',5,[(67.4,39.25),(67.4,38.45),(67.25,38.3)]),
    add('U18',6,[(68.05,39.75),(68.5,40.2)]),
    add('U18',7,[(67.4,40.25),(68.1,40.95),(68.5,41.35)]),
    add('U18',1,[(65.9,40.75),(65.9,41.65),(66,41.75)],.45,.2,.16),
    add('U18',4,[(64.8,39.25),(64.2,38.65),(64.2,38.2)],.45,.2,.16),
    add('U18',8,[(67.3,40.75),(67.3,41.8)],.45,.2,.16),
    add('U15',7,[(30.635,43.55)]),
]
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'exports/manual-supply-fanout.json').write_text(json.dumps({'moves_mm':moves,'fanouts':fanouts,'removed_routes':removed},indent=2),encoding='utf-8')
print('Created staggered power fanouts',len(fanouts),'moved components',moves)
for t in held:t.thisown=False
