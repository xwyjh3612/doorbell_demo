"""Keep the high-frequency switch loop local, above the exposed ground pad.

Retire the previous switch route; use a short pin neck and a broad same-side
connection into the inductor pad. Never route a switching node across the board.
"""
from pathlib import Path
import datetime, json, os, shutil, sys
import pcbnew as p
from comparison_route_geometry import b,FILE,pos,polys,layers,rules,outline
from shapely.geometry import LineString,Point

fps={f.GetReference():f for f in b.GetFootprints()}
d=next(d for d in fps['U15'].Pads() if d.GetNumber()=='3')
z=next(d for d in fps['L4'].Pads() if d.GetNumber()=='2')
assert d.GetNetname()==z.GetNetname()=='UPS_SW'
assert fps['U15'].GetLayer()==fps['L4'].GetLayer()==p.B_Cu
# Leave space below the broad horizontal segment for the EN pin's ordinary
# off-pad landing. A tight shortcut would trap that control pin on two layers.
path=[(pos(d),(30.635,43.0),.25),((30.635,43.0),(26.25,43.0),.6),((26.25,43.0),(26.25,43.6),.6)]
assert any(sh.contains(Point(26.25,43.6)) for sh in polys(z,p.B_Cu))
pad_conflicts=[];copper_conflicts=[]
for a,end,width in path:
    shape=LineString([a,end]).buffer(width/2+.201)
    assert outline.buffer(-.5).covers(LineString([a,end]).buffer(width/2))
    for f in b.GetFootprints():
        for pad in f.Pads():
            if pad.GetNetname()!=d.GetNetname() and pad.IsOnLayer(p.B_Cu) and any(shape.intersects(sh) for sh in polys(pad,p.B_Cu)):
                pad_conflicts.append([f.GetReference(),pad.GetNumber(),pad.GetNetname()])
    for t in b.GetTracks():
        if t.GetNetname()==d.GetNetname() or not t.IsOnLayer(p.B_Cu):
            continue
        sh=Point(pos(t)).buffer(p.ToMM(t.GetWidth(p.B_Cu))/2) if isinstance(t,p.PCB_VIA) else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2)
        if shape.intersects(sh):
            copper_conflicts.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()})
report={'path':path,'pad_conflicts':pad_conflicts,'other_copper_conflicts':copper_conflicts,'nominal_length_mm':sum(LineString([a,z]).length for a,z,w in path),'native_DRC_required':True}
(FILE.parent/'exports/short-switch-plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if '--preview' in sys.argv:
    print(json.dumps(report,indent=2));sys.exit()
assert not pad_conflicts,'No saved changes: short switch loop blocked by real pads'
snap=FILE.parent/'iterations'/('before-short-switch-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snap.mkdir(parents=True);shutil.copy2(FILE,snap/FILE.name)
held=[]
for t in list(b.GetTracks()):
    if t.GetNetname()=='UPS_SW':
        held.append(t);b.Remove(t)
for a,end,width in path:
    t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])))
    t.SetEnd(p.VECTOR2I(p.FromMM(end[0]),p.FromMM(end[1])))
    t.SetWidth(p.FromMM(width));t.SetLayer(p.B_Cu);t.SetNetCode(d.GetNetCode());t.SetLocked(True);b.Add(t)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
print('Saved local switch loop,',round(report['nominal_length_mm'],3),'mm; fresh native checks required.')
