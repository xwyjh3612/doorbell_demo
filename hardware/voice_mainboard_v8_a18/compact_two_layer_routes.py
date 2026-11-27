"""Merge exact collinear segments without changing copper paths or pad nets."""
from pathlib import Path
import collections, datetime, json, os, shutil
import pcbnew as p

FILE=Path(os.environ['A18_REPAIR_BOARD']).resolve()
OUT=FILE.parent
snap=OUT/'iterations'/('before-route-compaction-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snap.mkdir(parents=True)
shutil.copy2(FILE,snap/FILE.name)
from comparison_route_geometry import b
key=lambda v:(v.x,v.y)
protected={key(d.GetPosition()) for f in b.GetFootprints() for d in f.Pads()}
protected.update(key(t.GetPosition()) for t in b.GetTracks() if isinstance(t,p.PCB_VIA))
held=[];merged=0;retired=[]
reset=set(filter(None,os.environ.get('A18_RESET_NETS','').split(',')))
for t in list(b.GetTracks()):
    if t.GetNetname() in reset:
        retired.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()})
        held.append(t);b.Remove(t)
for iteration in range(18):
    nodes=collections.defaultdict(list)
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            continue
        for endpoint in [t.GetStart(),t.GetEnd()]:
            nodes[(t.GetNetCode(),t.GetLayer(),key(endpoint))].append(t)
    used=set();changes=0
    for (_,_,xy),edges in nodes.items():
        if xy in protected or len(edges)!=2:
            continue
        a,z=edges
        ids=[a.m_Uuid.AsString(),z.m_Uuid.AsString()]
        if any(uid in used for uid in ids) or a.GetWidth()!=z.GetWidth() or a.IsLocked()!=z.IsLocked():
            continue
        pa=key(a.GetEnd()) if key(a.GetStart())==xy else key(a.GetStart())
        pz=key(z.GetEnd()) if key(z.GetStart())==xy else key(z.GetStart())
        da=(pa[0]-xy[0],pa[1]-xy[1]);dz=(pz[0]-xy[0],pz[1]-xy[1])
        if da[0]*dz[1]!=da[1]*dz[0] or da[0]*dz[0]+da[1]*dz[1]>=0:
            continue
        a.SetStart(p.VECTOR2I(*pa));a.SetEnd(p.VECTOR2I(*pz))
        b.Remove(z);held.append(z);used.update(ids);changes+=1
    merged+=changes
    if not changes:
        break
if os.environ.get('A18_WIDEN_BOOST_SWITCH')=='1':
    for t in b.GetTracks():
        if not isinstance(t,p.PCB_VIA) and t.GetNetname()=='UPS_SW':
            t.SetWidth(p.FromMM(.6))
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE),b)
(OUT/'exports/route-compaction.json').write_text(json.dumps({'merged_collinear_segments':merged,'reset_routes':retired,'snapshot':str(snap),'native_DRC_required':True},indent=2),encoding='utf-8')
for t in held:
    t.thisown=False
print('Merged exact collinear segments:',merged)
