"""Reserve short, inspectable local ground connections and feedback return.

Route the boost feedback resistor to the controller's exposed ground pad,
join duplicated switch contacts and local decoupling grounds. Never alter pad
geometry or join CELL_NEG to GND. Disturbed copper is recorded for reconnection.
"""
import datetime,json,shutil
import pcbnew as p
from comparison_route_geometry import b,FILE,pos,polys,rules,outline,required_clearance
from shapely.geometry import Point,LineString

fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,number,index=0):return[d for d in fps[ref].Pads()if d.GetNumber()==str(number)][index]
plans=[
    ('button-ground',pad('SW1',2,1),pad('SW1',2,0),[],.25),
    ('level-shifter-ground',pad('U4',2),pad('U4',5),[],.2),
    ('boost-feedback-ground',pad('R62',2),pad('U15',9),[(35.075,46.5),(31,46.5),(31,46.8)],.25),
    ('charger-input-ground',pad('C67',2),pad('U16',9),[(47.95,46)],.3),
    ('output-cap-ground',pad('C66',2),pad('R63',2),[(37.2,53.2),(33.5,53.2)],.3),
]
snap=FILE.parent/'iterations'/('before-local-grounds-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snap.mkdir(parents=True);shutil.copy2(FILE,snap/FILE.name)
report=[];held=[]
for label,a,z,mids,width in plans:
    assert a.GetNetname()==z.GetNetname()=='GND'
    layer=a.GetParentFootprint().GetLayer();assert z.IsOnLayer(layer)
    path=[pos(a),*mids] if mids else[pos(a),pos(z)]
    if mids:assert any(sh.contains(Point(path[-1]))for sh in polys(z,layer))
    segments=[LineString([x,y])for x,y in zip(path,path[1:])]
    pads=[];obstacles=[]
    for line in segments:
        assert outline.buffer(-.5).covers(line.buffer(width/2))
        for f in b.GetFootprints():
            for d in f.Pads():
                if d.GetNetname()=='GND'or not d.IsOnLayer(layer):continue
                if any(line.buffer(width/2+required_clearance('GND',d.GetNetname())).intersects(sh)for sh in polys(d,layer)):pads.append([f.GetReference(),d.GetNumber(),d.GetNetname()])
        for zone,sh in rules:
            if zone.IsOnLayer(layer)and zone.GetDoNotAllowTracks()and line.buffer(width/2+.011).intersects(sh):pads.append(['rule-area'])
        for t in b.GetTracks():
            if t.GetNetname()=='GND'or not t.IsOnLayer(layer):continue
            shape=Point(pos(t)).buffer(p.ToMM(t.GetWidth(layer))/2)if isinstance(t,p.PCB_VIA)else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2)
            if line.buffer(width/2+required_clearance('GND',t.GetNetname())).intersects(shape):obstacles.append(t)
    entry={'name':label,'path_mm':path,'width_mm':width,'layer':p.LayerName(layer),'pad_conflicts':pads}
    if pads or any(t.IsLocked()for t in obstacles):
        entry['success']=False;report.append(entry);continue
    removed=[]
    for t in {t.m_Uuid.AsString():t for t in obstacles}.values():
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});held.append(t);b.Remove(t)
    for x,y in zip(path,path[1:]):
        t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(x[0]),p.FromMM(x[1])))
        t.SetEnd(p.VECTOR2I(p.FromMM(y[0]),p.FromMM(y[1])))
        t.SetWidth(p.FromMM(width));t.SetLayer(layer);t.SetNetCode(a.GetNetCode());t.SetLocked(True);b.Add(t)
    entry.update(success=True,removed_routes=removed);report.append(entry)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(FILE.parent/'exports/reserved-local-ground-paths.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for t in held:t.thisown=False
print(json.dumps({'planned':len(report),'connected':sum(q['success']for q in report),'failed':[q['name']for q in report if not q['success']],'disturbed_nets':sorted({t['net']for q in report for t in q.get('removed_routes',[])})},indent=2))
