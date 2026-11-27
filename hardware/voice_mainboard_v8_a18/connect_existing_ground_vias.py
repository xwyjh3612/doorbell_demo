"""Connect pad-bearing ground islands from existing clear off-pad vias."""
import json,math,time
from repair_comparison_groups import groups
from comparison_route_geometry import b,FILE,p,pos,route
report=[];started=time.monotonic()
for attempt in range(8):
 gs=groups('GND')
 if len(gs)<2:break
 main=max(gs,key=len);goals=[q for q in main if isinstance(q,p.PCB_VIA)]
 pairs=[]
 for g in gs:
  if g is main:continue
  for a in g:
   if not isinstance(a,p.PCB_VIA):continue
   for z in goals:pairs.append((math.dist(pos(a),pos(z)),a,z))
 success=False
 for _,a,z in sorted(pairs,key=lambda q:q[0])[:18]:
  if time.monotonic()-started>180:break
  entry={'from_mm':pos(a),'to_mm':pos(z),'width_mm':.16}
  try:
   entry.update(route('GND',pos(a),pos(z),{0,1},{0,1},width=.16),success=True)
   b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
   success=True
  except RuntimeError as error:entry.update(success=False,reason=str(error))
  report.append(entry)
  if success:break
 if not success:break
 print('Ground pad groups:',len(groups('GND')),flush=True)
(FILE.parent/'exports/existing-ground-via-connections.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Ground pad groups remaining:',len(groups('GND')),flush=True)
