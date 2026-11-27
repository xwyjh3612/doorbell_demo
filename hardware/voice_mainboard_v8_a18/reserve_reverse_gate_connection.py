"""Reserve the verified local gate pull-down connection above the input jack."""
import datetime,json,shutil,math
from comparison_route_geometry import b,FILE,p,pos,polys,rules,outline,required_clearance
from shapely.geometry import LineString,Point
fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,n):return next(d for d in fps[ref].Pads() if d.GetNumber()==str(n))
a,z=pad('R32',1),pad('Q6',1)
assert a.GetNetname()==z.GetNetname()=='REVERSE_GATE'
assert a.IsOnLayer(p.F_Cu) and z.IsOnLayer(p.F_Cu)
assert math.dist(pos(a),(64.675,35.75))<.001 and math.dist(pos(z),(59.0625,35.3))<.001
path=[pos(a),(64.4,35.475),(64.4,34.7),(59.6625,34.7),pos(z)]
segments=[LineString([x,y]) for x,y in zip(path,path[1:])];width=.16
obstacles={}
for line in segments:
 assert outline.buffer(-.5).covers(line.buffer(width/2))
 for f in b.GetFootprints():
  for d in f.Pads():
   if d.GetNetname()==a.GetNetname() or not d.IsOnLayer(p.F_Cu):continue
   assert not any(line.buffer(width/2+required_clearance(a.GetNetname(),d.GetNetname())).intersects(sh) for sh in polys(d,p.F_Cu)),(f.GetReference(),d.GetNumber())
 for rule,sh in rules:
  assert not(rule.IsOnLayer(p.F_Cu) and rule.GetDoNotAllowTracks() and line.buffer(width/2+.011).intersects(sh))
 for t in b.GetTracks():
  if not t.IsOnLayer(p.F_Cu) or t.GetNetname()==a.GetNetname():continue
  sh=Point(pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2) if isinstance(t,p.PCB_VIA) else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2)
  if line.buffer(width/2+required_clearance(a.GetNetname(),t.GetNetname())).intersects(sh):
   assert not t.IsLocked(),t.GetNetname()
   obstacles[t.m_Uuid.AsString()]=t
snapshot=FILE.parent/'iterations'/('before-gate-reservation-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True);shutil.copy2(FILE,snapshot/FILE.name)
held=[];retired=[]
for t in list(b.GetTracks()):
 if t.GetNetname()==a.GetNetname() or t.m_Uuid.AsString() in obstacles:
  retired.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});held.append(t);b.Remove(t)
for x,y in zip(path,path[1:]):
 t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(x[0]),p.FromMM(x[1])));t.SetEnd(p.VECTOR2I(p.FromMM(y[0]),p.FromMM(y[1])))
 t.SetWidth(p.FromMM(width));t.SetLayer(p.F_Cu);t.SetNetCode(a.GetNetCode());t.SetLocked(True);b.Add(t)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(FILE.parent/'exports/local-gate-reservation.json').write_text(json.dumps({'path_mm':path,'width_mm':width,'retired_copper':retired,'native_DRC_required':True},indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Reserved local gate wire; reconnect displaced nets:',sorted({q['net'] for q in retired if q['net']!=a.GetNetname()}))
