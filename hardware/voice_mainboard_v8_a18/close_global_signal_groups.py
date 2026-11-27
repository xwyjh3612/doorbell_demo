import os,json,math,time
from comparison_route_geometry import b,FILE,p,pos,layers,route
from repair_comparison_groups import groups,anchor_key
selected=os.environ['A18_ONLY_NETS'].split(',')
report=[]
for net in selected:
 entry={'net':net,'repairs':[],'errors':[]}
 while True:
  gs=groups(net,add_track_anchors=True)
  if len(gs)<2:break
  pairs=[]
  for i,g in enumerate(gs):
   for h in gs[i+1:]:
    for a in g:
     for z in h:
      pairs.append((math.dist(pos(a),pos(z)),a,z))
  # Give each physical group endpoint a chance; avoid repeating identical pads.
  prefer_vias=os.environ.get('A18_GLOBAL_PREFER_VIAS')=='1'
  pairs=sorted(pairs,key=lambda q:((2-int(isinstance(q[1],p.PCB_VIA))-int(isinstance(q[2],p.PCB_VIA)))if prefer_vias else 0,q[0],-sum(q[1].IsOnLayer(l)+q[2].IsOnLayer(l)for l in layers)))
  seen=set();found=False
  for _,a,z in pairs:
   sl={i for i,l in enumerate(layers)if a.IsOnLayer(l)}
   gl={i for i,l in enumerate(layers)if z.IsOnLayer(l)}
   key=(pos(a),tuple(sorted(sl)),pos(z),tuple(sorted(gl)))
   if key in seen:continue
   seen.add(key)
   if len(seen)>int(os.environ.get('A18_GLOBAL_PAIR_LIMIT','10')):break
   try:
    q=route(net,pos(a),pos(z),sl,gl,width=float(os.environ.get('A18_REPAIR_WIDTH','.16')),step=float(os.environ.get('A18_GLOBAL_ROUTE_GRID','.05')),bounds=(.5,.5,72.5,72.5))
    entry['repairs'].append({'from':pos(a),'to':pos(z),**q})
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    found=True;break
   except RuntimeError as e:entry['errors'].append(str(e))
  if not found:break
 entry['remaining_groups']=len(groups(net));report.append(entry)
 print(net,len(entry['repairs']),entry['remaining_groups'],flush=True)
 (FILE.parent/'exports/global-closure-progress.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
