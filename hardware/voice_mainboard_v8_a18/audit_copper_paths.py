"""Estimate routed path length/resistance from actual saved copper geometry.

This is a centreline estimate, not a field solver or current/thermal rating.
It excludes IC pad/contact resistance and does not solve parallel copper flow.
"""
from pathlib import Path
import collections, heapq, json, math, os, sys, hashlib
import pcbnew as p
SOURCE=Path(__file__).resolve().parent;sys.path.insert(0,str(SOURCE.parents[1]/'build/cad-tools/route-python'))
from shapely.geometry import Point,LineString
from shapely.ops import nearest_points
from shapely.strtree import STRtree
sys.path.insert(0,str(SOURCE))
from comparison_route_geometry import b,FILE,layers,polys,pos
fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,num):return next(d for d in fps[ref].Pads()if d.GetNumber()==str(num))
def trace_path(a,z):
    pa,pz=pad(*a),pad(*z);net=pa.GetNetname();assert net==pz.GetNetname(),(a,z)
    graph=collections.defaultdict(list);splits=collections.defaultdict(list);items=[];via_ids={}
    def key(item,layer):return (str(item.m_Uuid.AsString()),layer)
    def edge(a,z,r,length=0,width=None):
        graph[a].append((z,r,length,width));graph[z].append((a,r,length,width))
    for f in b.GetFootprints():
        for d in f.Pads():
            if d.GetNetname()!=net:continue
            keys=[]
            for layer in layers:
                if d.IsOnLayer(layer):
                    k=key(d,layer);keys.append(k)
                    for shape in polys(d,layer):items.append((layer,d,None,shape,k))
            for k in keys[1:]:edge(keys[0],k,0)
    for t in b.GetTracks():
        if t.GetNetname()!=net:continue
        if isinstance(t,p.PCB_VIA):
            keys=[key(t,layer)for layer in layers if t.IsOnLayer(layer)]
            barrel_r=1.724e-8*p.ToMM(b.GetDesignSettings().GetBoardThickness())*.001/(math.pi*p.ToMM(t.GetDrill())*.001*20e-6)
            for i,k in enumerate(keys):
                layer=k[1];items.append((layer,t,None,Point(pos(t)).buffer(p.ToMM(t.GetWidth(layer))/2),k));via_ids[k[0]]=barrel_r
                if i:edge(keys[i-1],k,barrel_r/(len(keys)-1))
        else:
            start,end=t.GetStart(),t.GetEnd();line=LineString([(p.ToMM(start.x),p.ToMM(start.y)),(p.ToMM(end.x),p.ToMM(end.y))])
            k=key(t,t.GetLayer());items.append((t.GetLayer(),t,line,line.buffer(p.ToMM(t.GetWidth())/2),k));splits[k].extend([0,line.length])
    for layer in layers:
        active=[x for x in items if x[0]==layer];shapes=[x[3]for x in active];tree=STRtree(shapes)
        for i,item in enumerate(active):
            for j in tree.query(item[3]):
                j=int(j)
                if j<=i or item[4]==active[j][4]or not item[3].intersects(active[j][3]):continue
                other=active[j]
                ca=item[2]if item[2]is not None else Point(pos(item[1]))
                cz=other[2]if other[2]is not None else Point(pos(other[1]))
                qa,qz=nearest_points(ca,cz);nodes=[]
                for obj,point in [(item,qa),(other,qz)]:
                    if obj[2]is None:nodes.append(obj[4])
                    else:
                        distance=round(obj[2].project(point),8);splits[obj[4]].append(distance);nodes.append((obj[4],distance))
                edge(nodes[0],nodes[1],0)
    for layer,t,line,shape,k in items:
        if line is None:continue
        width=p.ToMM(t.GetWidth());distances=sorted(set(round(x,8)for x in splits[k]))
        for x,y in zip(distances,distances[1:]):edge((k,x),(k,y),.000492571428571*(y-x)/width,y-x,width)
    starts=[key(pa,layer)for layer in layers if pa.IsOnLayer(layer)];goals={key(pz,layer)for layer in layers if pz.IsOnLayer(layer)}
    serial=0;queue=[];cost={};parent={}
    for k in starts:cost[k]=0;heapq.heappush(queue,(0,serial,k));serial+=1
    found=None
    while queue:
        r,_,node=heapq.heappop(queue)
        if r!=cost[node]:continue
        if node in goals:found=node;break
        for nxt,dr,length,width in graph[node]:
            if r+dr<cost.get(nxt,float('inf')):
                cost[nxt]=r+dr;parent[nxt]=(node,dr,length,width);heapq.heappush(queue,(r+dr,serial,nxt));serial+=1
    if found is None:return {'net':net,'from':a,'to':z,'trace_graph_connected':False,'scope':'No explicit-track path found; copper zones are not in this model.'}
    length=0;widths=[];via_steps=0;node=found
    while node in parent:
        before,dr,dl,w=parent[node];length+=dl
        if w is not None:widths.append(w)
        elif dr>0:via_steps+=1
        node=before
    return {'net':net,'from':a,'to':z,'trace_graph_connected':True,'centreline_length_mm':length,
            'minimum_width_mm_on_estimated_path':min(widths)if widths else None,'estimated_R_20C_ohm':cost[found],
            'estimated_drop_at_2A_V':2*cost[found],'via_layer_steps':via_steps}
pairs=[(('J1',4),('F1',1)),(('F1',2),('Q6',3)),(('Q6',2),('U18',3)),
       (('U18',2),('U2',4)),(('L1',2),('U1',42)),(('U15',7),('U18',6)),
       (('J23',1),('U15',4)),(('U17',2),('J23',2)),(('Q2',3),('U1',15)),
       (('U15',3),('L4',2)),(('U2',3),('L1',1)),(('U13',3),('L5',1)),
       (('J1',2),('J18',1)),(('U18',2),('U14',7)),(('U18',2),('U13',4))]
if __name__ == '__main__':
    if {'C75', 'C76'} <= fps.keys():
        pairs.extend([((ref, 1), ('U1', 42)) for ref in ('C6', 'C7', 'C75', 'C76')])
        pairs.append((('U1', 42), ('U1', 43)))
    results=[trace_path(a,z)for a,z in pairs]
    report={'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'copper_thickness_assumed_um':35,
            'via_plating_assumed_um':20,'paths':results,'actual_2A_qualified':False,
            'scope':'Centreline copper/via resistance estimate at 20C; excludes IC/contact/inductor resistance, source transients, temperature and parallel-current distribution.'}
    (FILE.parent/'exports/copper-path-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
