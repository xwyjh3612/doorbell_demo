"""Prune/trim dangling copper only after independent connectivity checks.

A long dangling trace can also serve intermediate junctions. Deleting it
wholesale is unsafe. Every removal or trim is tested against native DRC and
the net's physical pad groups before it is accepted into the real PCB.
"""
import datetime,hashlib,json,os,shutil,subprocess
from pathlib import Path
from comparison_route_geometry import b,FILE,p,pos,polys,layers
from repair_comparison_groups import groups
from shapely.geometry import Point,LineString,Polygon

repo=Path(__file__).resolve().parents[2]
cli=repo/'build/cad-tools/kicad/bin/kicad-cli.exe'
out=FILE.parent/'iterations'/('verified-stub-pruning-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True);shutil.copy2(FILE,out/('before-'+FILE.name))
trial=out/FILE.name
for suffix in ['.kicad_pro','.kicad_dru']:
 shutil.copy2(FILE.with_suffix(suffix),trial.with_suffix(suffix))
for name in ['fp-lib-table','sym-lib-table']:
 source=FILE.parent/name
 if source.exists():
  (out/name).write_text(source.read_text(encoding='utf-8').replace('${KIPRJMOD}',FILE.parent.as_posix()),encoding='utf-8')
held=[];changes=[];rejections=[]
def check():
 b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(trial),b)
 subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(out/'trial-drc.json'),str(trial)],check=True,capture_output=True)
 return json.loads((out/'trial-drc.json').read_text(encoding='utf-8'))
def hard(report):return sum(q['type'] not in ['track_dangling','via_dangling'] for q in report['violations'])
def coords(sh):
 if hasattr(sh,'geoms'):
  for q in sh.geoms:yield from coords(q)
 elif hasattr(sh,'coords'):yield from sh.coords
def trim_range(t):
 layer=t.GetLayer();start=t.GetStart();end=t.GetEnd()
 line=LineString([(p.ToMM(start.x),p.ToMM(start.y)),(p.ToMM(end.x),p.ToMM(end.y))]);width=p.ToMM(t.GetWidth());values=[]
 shapes=[]
 for f in b.GetFootprints():
  for d in f.Pads():
   if d.GetNetname()==t.GetNetname() and d.IsOnLayer(layer):shapes.extend(polys(d,layer))
 for q in b.GetTracks():
  if q==t or q.GetNetname()!=t.GetNetname() or not q.IsOnLayer(layer):continue
  if isinstance(q,p.PCB_VIA):shapes.append(Point(pos(q)).buffer(p.ToMM(q.GetWidth(layer))/2))
  else:shapes.append(LineString([(p.ToMM(q.GetStart().x),p.ToMM(q.GetStart().y)),(p.ToMM(q.GetEnd().x),p.ToMM(q.GetEnd().y))]).buffer(p.ToMM(q.GetWidth())/2))
 for z in b.Zones():
  if z.GetIsRuleArea() or z.GetNetname()!=t.GetNetname() or z.GetLayer()!=layer:continue
  ps=z.GetFilledPolysList(layer)
  for i in range(ps.OutlineCount()):
   q=ps.COutline(i);holes=[]
   for k in range(ps.HoleCount(i)):
    h=ps.CHole(i,k);holes.append([(p.ToMM(h.CPoint(j).x),p.ToMM(h.CPoint(j).y)) for j in range(h.PointCount())])
   shapes.append(Polygon([(p.ToMM(q.CPoint(j).x),p.ToMM(q.CPoint(j).y)) for j in range(q.PointCount())],holes))
 for sh in shapes:
  for xy in coords(line.intersection(sh.buffer(width/2))):values.append(line.project(Point(xy)))
 if not values:return None
 lo=max(0,min(values)-.01);hi=min(line.length,max(values)+.01)
 if lo<.02 and hi>line.length-.02:return None
 if hi-lo<.05:
  middle=(hi+lo)/2;lo=max(0,middle-.025);hi=min(line.length,middle+.025)
 return [line.interpolate(lo),line.interpolate(hi)]

report=check();assert hard(report)==0,'Fix non-dangling native violations before pruning'
for net in sorted({t.GetNetname() for t in b.GetTracks()}):
 orphan=groups(net,orphan_copper=True)
 if not orphan:continue
 before_groups=len(groups(net));before_unconnected=len(report['unconnected_items'])
 for t in orphan:b.Remove(t)
 candidate=check()
 if hard(candidate)==0 and len(candidate['unconnected_items'])<=before_unconnected and len(groups(net))<=before_groups:
  held.extend(orphan);report=candidate;p.SaveBoard(str(FILE),b)
  changes.append({'net':net,'action':'removed isolated copper without connected pads','count':len(orphan),'pad_groups_before':before_groups,'pad_groups_after':len(groups(net)),'native_unconnected_after':len(report['unconnected_items'])})
  print('Removed isolated copper',net,len(orphan),'native unconnected',len(report['unconnected_items']),flush=True)
 else:
  for t in orphan:b.Add(t)
  b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
for iteration in range(0 if os.environ.get('A18_PRUNE_ISOLATED_ONLY')=='1'
                       else int(os.environ.get('A18_PRUNE_PASSES', '6'))):
 count=0
 findings=[q for q in report['violations'] if q['type'] in ['via_dangling','track_dangling']]
 findings.sort(key=lambda q:q['type']!='via_dangling')
 for finding in findings:
  uid=finding['items'][0]['uuid'];objects={t.m_Uuid.AsString():t for t in b.GetTracks()}
  if uid not in objects:continue
  t=objects[uid];net=t.GetNetname();before_groups=len(groups(net));before_unconnected=len(report['unconnected_items'])
  # Open ends on an unfinished net are routing anchors. Native airwire counts
  # alone cannot protect the useful length of a planned, partially routed
  # branch. Keep it until the net is connected, then remove redundant stubs.
  if before_groups>1 and os.environ.get('A18_PRUNE_UNFINISHED')!='1':
   rejections.append({'uuid':uid,'net':net,'reason':'unfinished net routing anchor retained'});continue
  b.Remove(t);candidate=check()
  acceptable=lambda r:hard(r)==0 and len(r['unconnected_items'])<=before_unconnected and len(groups(net))<=before_groups
  if acceptable(candidate):
   held.append(t);report=candidate;action='removed'
  else:
   b.Add(t);b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
   if isinstance(t,p.PCB_VIA):rejections.append({'uuid':uid,'net':net,'reason':'removal changed connectivity'});continue
   bounds=trim_range(t)
   if not bounds:rejections.append({'uuid':uid,'net':net,'reason':'needed intermediate connections retained'});continue
   oldstart=p.VECTOR2I(t.GetStart().x,t.GetStart().y);oldend=p.VECTOR2I(t.GetEnd().x,t.GetEnd().y)
   t.SetStart(p.VECTOR2I(p.FromMM(bounds[0].x),p.FromMM(bounds[0].y)));t.SetEnd(p.VECTOR2I(p.FromMM(bounds[1].x),p.FromMM(bounds[1].y)))
   candidate=check()
   if not acceptable(candidate):
    t.SetStart(oldstart);t.SetEnd(oldend);b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
    rejections.append({'uuid':uid,'net':net,'reason':'trim changed connectivity'});continue
   report=candidate;action='trimmed'
  changes.append({'uuid':uid,'net':net,'action':action,'pad_groups_before':before_groups,'pad_groups_after':len(groups(net)),'native_unconnected_after':len(report['unconnected_items'])})
  count+=1;p.SaveBoard(str(FILE),b)
  print(action,net,'DRC',len(report['violations']),'unconnected',len(report['unconnected_items']),flush=True)
 if not count:break
report=check();p.SaveBoard(str(FILE),b)
(FILE.parent/'exports/verified-stub-pruning.json').write_text(json.dumps({'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'changes':changes,'retained_findings':rejections,'native_counts':{k:len(report[k]) for k in ['violations','unconnected_items']},'scope':'Each candidate independently checked with native rules and physical pad groups; no pad/rule changes.'},indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Verified pruning finished:',len(changes),'changes; native',len(report['violations']),len(report['unconnected_items']),flush=True)
