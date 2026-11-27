"""Reserve an explicit 0.5mm power return between plated ground terminals.

This avoids relying on microscopic zone corner contacts or a signal-width
ground neck. Native DRC and copper resistance/thermal review remain mandatory.
"""
import datetime,json,math,shutil
from comparison_route_geometry import b,FILE,p,pos,polys,rules,outline,required_clearance
from shapely.geometry import LineString,Point
fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,n):return next(d for d in fps[ref].Pads() if d.GetNumber()==str(n))
a,z=pad('J1',2),pad('J18',1)
assert a.GetNetname()==z.GetNetname()=='GND'
assert a.GetAttribute()==z.GetAttribute()==p.PAD_ATTRIB_PTH
assert math.dist(pos(a),(61.45,39.4))<.001 and math.dist(pos(z),(63,56))<.001
path=[pos(a),(61.6,39.25),(69.2,39.25),(71.8,41.85),(71.8,54.3),(64.7,54.3),pos(z)]
width=.5;obstacles={}
for x,y in zip(path,path[1:]):
 line=LineString([x,y]);assert outline.buffer(-.5).covers(line.buffer(width/2))
 for f in b.GetFootprints():
  for d in f.Pads():
   if d.GetNetname()=='GND' or not d.IsOnLayer(p.F_Cu):continue
   assert not any(line.buffer(width/2+required_clearance('GND',d.GetNetname())).intersects(sh) for sh in polys(d,p.F_Cu)),(f.GetReference(),d.GetNumber())
 for rule,sh in rules:assert not(rule.IsOnLayer(p.F_Cu) and rule.GetDoNotAllowTracks() and line.buffer(width/2+.011).intersects(sh))
 for t in b.GetTracks():
  if not t.IsOnLayer(p.F_Cu) or t.GetNetname()=='GND':continue
  sh=Point(pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2) if isinstance(t,p.PCB_VIA) else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2)
  if line.buffer(width/2+required_clearance('GND',t.GetNetname())).intersects(sh):
   assert not t.IsLocked(),t.GetNetname();obstacles[t.m_Uuid.AsString()]=t
snapshot=FILE.parent/'iterations'/('before-wide-ground-return-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True);shutil.copy2(FILE,snapshot/FILE.name)
held=[];retired=[]
for t in obstacles.values():retired.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});held.append(t);b.Remove(t)
for x,y in zip(path,path[1:]):
 t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(x[0]),p.FromMM(x[1])));t.SetEnd(p.VECTOR2I(p.FromMM(y[0]),p.FromMM(y[1])))
 t.SetWidth(p.FromMM(width));t.SetLayer(p.F_Cu);t.SetNetCode(a.GetNetCode());t.SetLocked(True);b.Add(t)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
report={'from':'J1.2','to':'J18.1','path_mm':path,'width_mm':width,'layers':['F.Cu'],'new_vias':0,'retired_copper':retired,'native_DRC_required':True,'actual_2A_qualified':False}
(FILE.parent/'exports/wide-ground-return.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Reserved power return; reconnect displaced nets:',sorted({q['net'] for q in retired}),flush=True)
