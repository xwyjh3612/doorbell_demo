"""Connect physical pad groups, avoiding ambiguous airwire track midpoints.

Connectivity is recomputed geometrically after each mutation. A final native
KiCad connectivity/clearance report is the independent acceptance check.
"""
from pathlib import Path
import collections,json,math,os,sys,time
import pcbnew as p
from repair_connections import b,FILE,route,pos,polys,layers
from shapely.geometry import Polygon,Point,LineString
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parent

def groups(net):
    pads=[d for f in b.GetFootprints()for d in f.Pads()if d.GetNetname()==net]
    objects=[*pads,*[t for t in b.GetTracks()if t.GetNetname()==net]]
    zones=[]
    for z in b.Zones():
        if z.GetIsRuleArea()or z.GetNetname()!=net:continue
        shape=z.GetFilledPolysList(z.GetLayer())
        for i in range(shape.OutlineCount()):
            q=shape.COutline(i);holes=[]
            for k in range(shape.HoleCount(i)):
                h=shape.CHole(i,k);holes.append([(p.ToMM(h.CPoint(j).x),p.ToMM(h.CPoint(j).y))for j in range(h.PointCount())])
            zones.append((z.GetLayer(),Polygon([(p.ToMM(q.CPoint(j).x),p.ToMM(q.CPoint(j).y))for j in range(q.PointCount())],holes).buffer(0)))
    parent=list(range(len(objects)+len(zones)))
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def join(a,z):parent[find(a)]=find(z)
    for layer in layers:
        shapes=[];owners=[]
        for i,obj in enumerate(objects):
            if not obj.IsOnLayer(layer):continue
            if isinstance(obj,p.PAD):ss=polys(obj,layer)
            elif isinstance(obj,p.PCB_VIA):ss=[Point(pos(obj)).buffer(p.ToMM(obj.GetWidth(layer))/2)]
            else:
                a,z=obj.GetStart(),obj.GetEnd()
                ss=[LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]).buffer(p.ToMM(obj.GetWidth())/2)]
            shapes.extend(ss);owners.extend([i]*len(ss))
        for j,(zl,sh)in enumerate(zones):
            if zl==layer:shapes.append(sh);owners.append(len(objects)+j)
        if not shapes:continue
        tree=STRtree(shapes)
        for i,sh in enumerate(shapes):
            for j in tree.query(sh):
                if owners[i]!=owners[int(j)]and sh.intersects(shapes[int(j)]):join(owners[i],owners[int(j)])
    result=collections.defaultdict(list)
    for i,d in enumerate(pads):result[find(i)].append(d)
    # An existing narrow pad neck is already electrically connected. Start
    # the broad continuation at its off-pad via rather than attempting to
    # route a wider wire through the narrow neck a second time.
    for i,obj in enumerate(objects[len(pads):],start=len(pads)):
        if isinstance(obj,p.PCB_VIA)and find(i)in result:result[find(i)].append(obj)
    return list(result.values())

if __name__=='__main__':
    grid=float(os.environ.get('A18_ROUTE_GRID','.1'))
    report=[];allnets=collections.Counter(d.GetNetname()for f in b.GetFootprints()for d in f.Pads()if d.GetNetname()and not d.GetNetname().startswith('unconnected-'))
    # Small local nets first; major rails already have reserved broad paths.
    ordered=sorted(allnets,key=lambda n:(n=='GND',n in ['ESP_3V3','SYS_5V','VIN_PROTECTED','BAT_BOOST_5V','MODEM_3V8','BAT_SENSE_IN','CELL_NEG'],allnets[n]))
    for net in ordered:
        failures=set();start=time.monotonic();entry={'net':net,'repairs':[],'failed_searches':[]}
        for attempt in range(30):
            gs=groups(net)
            if len(gs)<2:break
            candidates=[]
            for i,g in enumerate(gs):
                for h in gs[i+1:]:
                    for a in g:
                        for z in h:
                            key=tuple(sorted([str(a.m_Uuid.AsString()),str(z.m_Uuid.AsString())]))
                            if key not in failures:candidates.append((math.dist(pos(a),pos(z)),key,a,z))
            if not candidates:break
            ok=False
            for _,key,a,z in sorted(candidates,key=lambda q:q[0])[:6]:
                sl={i for i,l in enumerate(layers)if a.IsOnLayer(l)};gl={i for i,l in enumerate(layers)if z.IsOnLayer(l)}
                width=.5 if net in ['VIN_DC','VIN_FUSED']else(.4 if net in ['SPK_PLUS','SPK_MINUS']else(.25 if net in ['ESP_3V3','SYS_5V','VIN_PROTECTED','BAT_BOOST_5V','MODEM_3V8','BAT_SENSE_IN','CELL_NEG']else .2))
                try:
                    pa,pz=pos(a),pos(z)
                    bounds=None if grid>=.1 else(max(.5,min(pa[0],pz[0])-6),max(.5,min(pa[1],pz[1])-6),min(72.5,max(pa[0],pz[0])+6),min(72.5,max(pa[1],pz[1])+6))
                    change=route(net,pa,pz,sl,gl,width=width,step=grid,bounds=bounds)
                    entry['repairs'].append({'from':pos(a),'to':pos(z),'width':width,**change});ok=True
                    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b);break
                except RuntimeError as error:
                    failures.add(key)
                    entry['failed_searches'].append({'from':pos(a),'to':pos(z),'reason':str(error)})
            if not ok:break
        entry.update(remaining_pad_groups=len(groups(net)),seconds=time.monotonic()-start)
        report.append(entry);print(net,'repairs',len(entry['repairs']),'groups',entry['remaining_pad_groups'],'seconds',round(entry['seconds'],1),flush=True)
        (ROOT/'exports/pad-group-progress.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    (ROOT/'exports/pad-group-connections.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
