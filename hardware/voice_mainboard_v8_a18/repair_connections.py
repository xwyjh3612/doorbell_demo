"""Repair specific native DRC airwires with geometric two-layer searches.

Preserves pad nets and checks copper/holes/rule-area obstacles. Changes still
require a fresh independent KiCad DRC. No DRC exclusions are generated here.
"""
from pathlib import Path
import heapq, json, math, re, sys, time, types
import pcbnew as p
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO/'build/cad-tools/route-python'))
import numpy as np
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import unary_union
from shapely import contains_xy

FILE = ROOT/'voice_mainboard_v8_a18.kicad_pcb'
b = p.LoadBoard(str(FILE))
def pos(item):
    return p.ToMM(item.GetPosition().x), p.ToMM(item.GetPosition().y)
def polys(pad, layer):
    shape = pad.GetEffectivePolygon(layer)
    return [Polygon([(p.ToMM(q.CPoint(j).x), p.ToMM(q.CPoint(j).y)) for j in range(q.PointCount())])
            for q in [shape.COutline(i) for i in range(shape.OutlineCount())] if q.PointCount() >= 3]
def rule_shapes():
    result=[]
    for z in [*b.Zones(), *[z for f in b.GetFootprints() for z in f.Zones()]]:
        if not z.GetIsRuleArea(): continue
        for i in range(z.Outline().OutlineCount()):
            ring=z.Outline().COutline(i)
            shape=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
            result.append((z,shape))
    return result
rules=rule_shapes()
outline=Polygon(json.loads((ROOT/'design.json').read_text(encoding='utf-8'))['mechanical']['outline_mm'])
layers=[p.F_Cu,p.B_Cu]
def route(net,src,goal,source_layers,goal_layers,width=.2,step=.1,bounds=None):
    clearance=.201+width/2
    obstacles=[[]for _ in layers];vias=[];reuse=[]
    for f in b.GetFootprints():
        for d in f.Pads():
            for li,layer in enumerate(layers):
                if not d.IsOnLayer(layer):continue
                for sh in polys(d,layer):
                    if d.GetNetname()!=net:obstacles[li].append(sh.buffer(clearance))
                    # Conventional off-pad vias, including same-net SMT pads.
                    vias.append(sh.buffer(.35 if d.GetNetname()==net else .511))
            if d.GetDrillSize().x:
                hole=Point(pos(d)).buffer(p.ToMM(d.GetDrillSize().x)/2+.555)
                vias.append(hole)
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            sh=Point(pos(t));radius=p.ToMM(t.GetWidth(p.F_Cu))/2
            vias.append(sh.buffer(p.ToMM(t.GetDrill())/2+.405))
            if t.GetNetname()==net:
                reuse.append(sh.buffer(max(.075,radius-.04)))
                continue
            for li in range(2):obstacles[li].append(sh.buffer(radius+clearance))
            vias.append(sh.buffer(radius+.511))
        else:
            if t.GetNetname()==net:continue
            a,z=t.GetStart(),t.GetEnd()
            sh=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))])
            radius=p.ToMM(t.GetWidth())/2
            obstacles[layers.index(t.GetLayer())].append(sh.buffer(radius+clearance))
            vias.append(sh.buffer(radius+.511))
    for z,sh in rules:
        for li,layer in enumerate(layers):
            if z.IsOnLayer(layer)and z.GetDoNotAllowTracks():obstacles[li].append(sh.buffer(width/2+.011))
        if z.GetDoNotAllowVias():vias.append(sh.buffer(.311))
    obstacles=[unary_union(x)for x in obstacles]
    via_obstacle=unary_union(vias);reuse_shape=unary_union(reuse)
    # Each endpoint lies exactly on a grid anchor or uses exact final geometry.
    bounds=(.5,.5,72.5,72.5)if bounds is None else bounds
    x0=src[0]+math.floor((bounds[0]-src[0])/step)*step;y0=src[1]+math.floor((bounds[1]-src[1])/step)*step
    xs=x0+np.arange(math.ceil((bounds[2]-x0)/step)+1)*step
    ys=y0+np.arange(math.ceil((bounds[3]-y0)/step)+1)*step
    xx,yy=np.meshgrid(xs,ys)
    grids=[contains_xy(o,xx,yy)|~contains_xy(outline.buffer(-width/2-.011),xx,yy)for o in obstacles]
    via_grid=contains_xy(via_obstacle,xx,yy)|~contains_xy(outline.buffer(-.311),xx,yy)
    reuse_grid=contains_xy(reuse_shape,xx,yy)
    sx,sy=round((src[0]-x0)/step),round((src[1]-y0)/step)
    gx,gy=round((goal[0]-x0)/step),round((goal[1]-y0)/step)
    goal_nodes=set()
    for li in goal_layers:
        for dx in range(-2,3):
            for dy in range(-2,3):
                tx,ty=gx+dx,gy+dy
                if not(0<=tx<len(xs)and 0<=ty<len(ys))or grids[li][ty,tx]:continue
                point=(float(xs[tx]),float(ys[ty]))
                if not obstacles[li].intersects(LineString([point,goal])):goal_nodes.add((tx,ty,li))
    costs={};parent={};heap=[];found=None;deadline=time.monotonic()+45
    for li in source_layers:
        if not grids[li][sy,sx]:costs[(sx,sy,li)]=0;heapq.heappush(heap,(math.hypot(sx-gx,sy-gy),0,(sx,sy,li)))
    visited=0
    while heap:
        _,cost,node=heapq.heappop(heap)
        if cost!=costs.get(node):continue
        visited+=1
        if visited%2000==0 and time.monotonic()>deadline:raise RuntimeError('search time limit')
        x,y,li=node
        if node in goal_nodes:found=node;break
        candidates=[(x+dx,y+dy,li,cost+(math.sqrt(2)if dx and dy else 1))
                    for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]]
        if reuse_grid[y,x]or not via_grid[y,x]:candidates.append((x,y,1-li,cost+(5 if reuse_grid[y,x]else 18)))
        for tx,ty,k,newcost in candidates:
            if not(0<=tx<len(xs)and 0<=ty<len(ys))or grids[k][ty,tx]:continue
            if k==li and tx!=x and ty!=y and(grids[k][y,tx]or grids[k][ty,x]):continue
            nxt=(tx,ty,k)
            if newcost<costs.get(nxt,float('inf')):
                costs[nxt]=newcost;parent[nxt]=node
                heapq.heappush(heap,(newcost+math.hypot(tx-gx,ty-gy),newcost,nxt))
    if found is None:raise RuntimeError('no clear route; visited='+str(visited)+' source blocked='+str([bool(grids[li][sy,sx])for li in source_layers])+' reachable goal anchors='+str(len(goal_nodes)))
    nodes=[found]
    while nodes[-1]in parent:nodes.append(parent[nodes[-1]])
    nodes.reverse();groups=[];current=[src];li=nodes[0][2];newvias=[]
    for x,y,k in nodes[1:]:
        xy=(float(xs[x]),float(ys[y]))
        if k!=li:
            groups.append((li,current))
            if not reuse_shape.intersects(Point(xy)):newvias.append(xy)
            current=[xy];li=k
        else:current.append(xy)
    if math.dist(current[-1],goal)>1e-8:current.append(goal)
    groups.append((li,current));segments=[]
    for li,points in groups:
        compact=[points[0]];i=0
        while i<len(points)-1:
            j=len(points)-1
            while j>i and obstacles[li].intersects(LineString([points[i],points[j]])):j-=1
            if j==i:raise RuntimeError('exact clearance failed on grid path')
            compact.append(points[j]);i=j
        segments.extend((layers[li],a,z)for a,z in zip(compact,compact[1:])if math.dist(a,z)>1e-6)
    for layer,a,z in segments:
        t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])))
        t.SetEnd(p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1])));t.SetWidth(p.FromMM(width));t.SetLayer(layer)
        t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
    for xy in newvias:
        t=p.PCB_VIA(b);t.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
        t.SetWidth(p.FromMM(.6));t.SetDrill(p.FromMM(.3));t.SetViaType(p.VIATYPE_THROUGH)
        t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
    return {'segments':len(segments),'new_vias':len(newvias)}

def item_index():
    return {str(x.m_Uuid.AsString()):x for x in [*[d for f in b.GetFootprints()for d in f.Pads()],*b.GetTracks(),*b.Zones()]}
if __name__=='__main__':
    drc=Path(sys.argv[1]);report=json.loads(drc.read_text(encoding='utf-8'));items=item_index();changes=[]
    for error in report['unconnected_items']:
        a,z=error['items'];ea=items.get(a['uuid']);ez=items.get(z['uuid'])
        if ea is None or ez is None or isinstance(ea,p.ZONE)or isinstance(ez,p.ZONE):continue
        net=ea.GetNetname();assert net==ez.GetNetname()
        src=(a['pos']['x'],a['pos']['y']);goal=(z['pos']['x'],z['pos']['y'])
        sl={i for i,l in enumerate(layers)if ea.IsOnLayer(l)};gl={i for i,l in enumerate(layers)if ez.IsOnLayer(l)}
        start=time.monotonic();entry={'net':net,'from':src,'to':goal}
        try:entry.update(route(net,src,goal,sl,gl,width=.2 if net not in ['VIN_DC','VIN_FUSED']else .5),success=True)
        except RuntimeError as e:entry.update(success=False,reason=str(e))
        entry['seconds']=time.monotonic()-start;changes.append(entry)
        p.SaveBoard(str(FILE),b)
        print(net,entry['success'],entry.get('reason',''),round(entry['seconds'],2),flush=True)
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    (ROOT/'exports'/('repairs-'+drc.stem+'.json')).write_text(json.dumps(changes,indent=2),encoding='utf-8')
