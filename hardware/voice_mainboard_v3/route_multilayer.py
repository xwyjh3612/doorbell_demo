"""Collision-checked three-layer escape routing, preserving In1 ground.

Conventional 0.6/0.3mm vias are allowed only clear of every pad and track.
All added copper remains subject to KiCad's independent DRC.
"""
import heapq,math
from shapely.geometry import Point,LineString
from shapely.ops import unary_union
from shapely import contains_xy
import numpy as np
def route(r,start,end,width=.2,bounds=(1.6,1.6,98.4,73.4),step=.1):
    p=r.p;b=r.board;a,z=r.pad(*start),r.pad(*end);net=a.GetNetname();assert net==z.GetNetname()
    src,goal=r.pos(a),r.pos(z);layers=[p.F_Cu,p.B_Cu,p.In2_Cu]
    source_layers={i for i,layer in enumerate(layers)if not hasattr(a,'IsOnLayer')or a.IsOnLayer(layer)}
    goal_layers={i for i,layer in enumerate(layers)if not hasattr(z,'IsOnLayer')or z.IsOnLayer(layer)}
    obstacles=[];via_obstacles=[];existing_net_vias=[];clearance=.205+width/2
    for layer in layers:
        shapes=[]
        for fp in b.GetFootprints():
            for pd in fp.Pads():
                if pd.IsOnLayer(layer)and pd.GetNetname()!=net:shapes.extend(sh.buffer(clearance)for sh in r.polygons(pd,layer))
        for t in b.GetTracks():
            if t.GetNetname()==net:continue
            if isinstance(t,p.PCB_VIA):sh=Point(r.pos(t));rad=p.ToMM(t.GetWidth(layer))/2
            elif t.GetLayer()==layer:sh=LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]);rad=p.ToMM(t.GetWidth())/2
            else:continue
            shapes.append(sh.buffer(rad+clearance))
        obstacles.append(unary_union(shapes))
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            for layer in [p.F_Cu,p.B_Cu]:
                if pd.IsOnLayer(layer):via_obstacles.extend(sh.buffer(.505)for sh in r.polygons(pd,layer))
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            sh=Point(r.pos(t));rad=p.ToMM(t.GetWidth(p.F_Cu))/2
            if t.GetNetname()==net:existing_net_vias.append(sh.buffer(max(.08,rad-.06)))
        else:sh=LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]);rad=p.ToMM(t.GetWidth())/2
        via_obstacles.append(sh.buffer(rad+.505))
    via_obstacle=unary_union(via_obstacles)
    x0=src[0]+math.floor((bounds[0]-src[0])/step)*step;y0=src[1]+math.floor((bounds[1]-src[1])/step)*step
    xs=x0+np.arange(math.ceil((bounds[2]-x0)/step)+1)*step;ys=y0+np.arange(math.ceil((bounds[3]-y0)/step)+1)*step
    xx,yy=np.meshgrid(xs,ys);grids=[contains_xy(o,xx,yy)for o in obstacles];via_grid=contains_xy(via_obstacle,xx,yy)
    reuse_shape=unary_union(existing_net_vias);reuse_grid=contains_xy(reuse_shape,xx,yy)
    sx,sy=round((src[0]-x0)/step),round((src[1]-y0)/step);gx,gy=round((goal[0]-x0)/step),round((goal[1]-y0)/step)
    costs={};parent={};heap=[];visited=0;found=None
    for li in source_layers:
        if not grids[li][sy,sx]:costs[(sx,sy,li)]=0;heapq.heappush(heap,(math.hypot(sx-gx,sy-gy),0,(sx,sy,li)))
    while heap:
        _,cost,node=heapq.heappop(heap)
        if cost!=costs.get(node):continue
        visited+=1;x,y,li=node
        if(x,y)==(gx,gy)and li in goal_layers:found=node;break
        candidates=[(x+dx,y+dy,li,cost+1)for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]]
        if reuse_grid[y,x]or not via_grid[y,x]:candidates.extend((x,y,k,cost+(5 if reuse_grid[y,x]else 20))for k in range(3)if k!=li)
        for tx,ty,k,newcost in candidates:
            if not(0<=tx<len(xs)and 0<=ty<len(ys))or grids[k][ty,tx]:continue
            if k==li:
                aa=src if(x,y)==(sx,sy)else(float(xs[x]),float(ys[y]));zz=goal if(tx,ty)==(gx,gy)else(float(xs[tx]),float(ys[ty]))
                if obstacles[k].intersects(LineString([aa,zz])):continue
            nxt=(tx,ty,k)
            if newcost<costs.get(nxt,float('inf')):
                costs[nxt]=newcost;parent[nxt]=node;heapq.heappush(heap,(newcost+math.hypot(tx-gx,ty-gy),newcost,nxt))
    if found is None:raise RuntimeError('No multilayer path '+net+' visited '+str(visited))
    nodes=[found]
    while nodes[-1]in parent:nodes.append(parent[nodes[-1]])
    nodes.reverse();groups=[];current=[src];li=nodes[0][2];vias=[]
    for x,y,k in nodes[1:]:
        xy=(float(xs[x]),float(ys[y]))
        if k!=li:
            groups.append((li,current))
            if not reuse_shape.intersects(Point(xy)):vias.append(xy)
            current=[xy];li=k
        else:current.append(xy)
    current[-1]=goal;groups.append((li,current))
    for layer,points in groups:
        compact=[points[0]];i=0
        while i<len(points)-1:
            j=len(points)-1
            while j>i+1 and obstacles[layer].intersects(LineString([points[i],points[j]])):j-=1
            compact.append(points[j]);i=j
        for aa,zz in zip(compact,compact[1:]):
            if math.dist(aa,zz)<1e-6:continue
            assert not obstacles[layer].intersects(LineString([aa,zz]))
            r.direct(net,[aa,zz],width,layers[layer])
    for i,xy in enumerate(vias):r.addvia('ml_'+net+'_'+str(i),net,xy)
    print(net,'multilayer routed; vias',len(vias),'visited',visited,flush=True)
    return {'layers':[b.GetLayerName(layers[k])for k,_ in groups],'new_vias':len(vias)}
