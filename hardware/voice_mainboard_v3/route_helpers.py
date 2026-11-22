from pathlib import Path
import sys,heapq,math,json
import pcbnew as p
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
import numpy as np
from shapely.geometry import Point,LineString,Polygon
from shapely.ops import unary_union
from shapely import contains_xy
board=p.LoadBoard(sys.argv[1])
removed=[]
# Release EN's old detour to make the VIN pad's perpendicular exit possible.
for t in list(board.GetTracks()):
    if False:removed.append(t);board.Remove(t)
virtual={}
def pad(ref,n):
    if ref in virtual:return virtual[ref]
    return next(pd for fp in board.GetFootprints() if fp.GetReference()==ref for pd in fp.Pads() if pd.GetNumber()==str(n))
class Endpoint:
    def __init__(self,net,xy):self.net=net;self.xy=xy
    def GetNetname(self):return self.net
    def GetNetCode(self):return board.FindNet(self.net).GetNetCode()
    def GetPosition(self):return p.VECTOR2I(p.FromMM(self.xy[0]),p.FromMM(self.xy[1]))
def addvia(ref,net,xy,diameter=.6,drill=.3):
    virtual[ref]=Endpoint(net,xy)
    v=p.PCB_VIA(board);v.SetPosition(virtual[ref].GetPosition());v.SetWidth(p.FromMM(diameter));v.SetDrill(p.FromMM(drill));v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNetCode(virtual[ref].GetNetCode());board.Add(v)
def direct(net,nodes,width=.2,layer=p.F_Cu):
    for a,z in zip(nodes,nodes[1:]):
        t=p.PCB_TRACK(board);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])));t.SetEnd(p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1])));t.SetWidth(p.FromMM(width));t.SetLayer(layer);t.SetNetCode(board.FindNet(net).GetNetCode());board.Add(t)
def escapevia(ref,start,diameter=.6,drill=.3,neck=.2,layer=None):
    pd=pad(*start);net=pd.GetNetname();xy=pos(pd);all_obstacles=[];front=[]
    # PAD.GetLayer() remains F.Cu for some flipped footprint pads in KiCad's
    # SWIG API; the pad layer mask is the authoritative copper membership.
    layer=(p.F_Cu if pd.IsOnLayer(p.F_Cu)else p.B_Cu)if layer is None else layer
    for fp in board.GetFootprints():
        for pp in fp.Pads():
            shapes=(polygons(pp,p.F_Cu)if pp.IsOnLayer(p.F_Cu)else[])+(polygons(pp,p.B_Cu)if pp.IsOnLayer(p.B_Cu)else[])
            # A same-net SMT pad permits a conventional tented via beside its
            # copper edge. Keep the entire via annulus outside the solder pad;
            # never put its drill/paste aperture inside that pad.
            pad_gap=.05 if pp.GetNetname()==net and pp.GetAttribute()==p.PAD_ATTRIB_SMD else .201
            all_obstacles.extend(sh.buffer(diameter/2+pad_gap)for sh in shapes)
            if pp.GetNetname()!=net and pp.IsOnLayer(layer):front.extend(sh.buffer(neck/2+.205)for sh in polygons(pp,layer))
    for t in board.GetTracks():
        if isinstance(t,p.PCB_VIA):
            # Drill clearance applies even to vias on the same electrical net.
            all_obstacles.append(Point(pos(t)).buffer(drill/2+p.ToMM(t.GetDrill())/2+.255))
        if t.GetNetname()==net:continue
        if isinstance(t,p.PCB_VIA):shape=Point(pos(t));radius=p.ToMM(t.GetWidth(p.F_Cu))/2
        else:
            a,z=t.GetStart(),t.GetEnd();shape=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]);radius=p.ToMM(t.GetWidth())/2
        all_obstacles.append(shape.buffer(radius+diameter/2+.201))
        if isinstance(t,p.PCB_VIA)or t.GetLayer()==layer:front.append(shape.buffer(radius+neck/2+.205))
    blocked=unary_union(all_obstacles);fblocked=unary_union(front)
    # Reuse a reachable existing via on this net. Same-net copper clearance
    # does not permit drilling two holes almost on top of each other.
    for t in board.GetTracks():
        if not isinstance(t,p.PCB_VIA)or t.GetNetname()!=net:continue
        z=pos(t)
        if .5<=math.dist(xy,z)<=4 and not fblocked.intersects(LineString([xy,z])):
            virtual[ref]=Endpoint(net,z);direct(net,[xy,z],neck,layer)
            print('Reused escape via',ref,z,flush=True);return
    candidates=[(round(xy[0]/.1)*.1+dx*.1,round(xy[1]/.1)*.1+dy*.1)for dx in range(-25,26)for dy in range(-25,26)]
    for z in sorted(candidates,key=lambda z:math.dist(xy,z)):
        if math.dist(xy,z)<.5 or blocked.intersects(Point(z))or fblocked.intersects(LineString([xy,z])):continue
        addvia(ref,net,z,diameter,drill);direct(net,[xy,z],neck,layer);print('Escape via',ref,z,flush=True);return
    # Dense signal crossings may need a bent escape rather than a straight
    # neck. Search the front layer once, then choose a through-via location
    # that clears copper and pads on every layer.
    step=.025;span=4.0;x0=xy[0]-span;y0=xy[1]-span
    xs=x0+np.arange(round(2*span/step)+1)*step
    ys=y0+np.arange(round(2*span/step)+1)*step
    xx,yy=np.meshgrid(xs,ys)
    blocked_grid=contains_xy(fblocked,xx,yy)
    via_grid=contains_xy(blocked,xx,yy)
    s=(round(span/step),round(span/step))
    if blocked_grid[s[1],s[0]]:raise RuntimeError('Escape source blocked '+str(start))
    costs={s:0};parent={};heap=[(0,s)];found=None
    while heap:
        cost,node=heapq.heappop(heap)
        if cost!=costs.get(node):continue
        x,y=node;z=(float(xs[x]),float(ys[y]))
        if not via_grid[y,x] and math.dist(xy,z)>=.5:
            found=node;break
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]:
            tx,ty=x+dx,y+dy
            if not(0<=tx<len(xs) and 0<=ty<len(ys))or blocked_grid[ty,tx]:continue
            if dx and dy and(blocked_grid[y,tx]or blocked_grid[ty,x]):continue
            nxt=(tx,ty);c=cost+(math.sqrt(2)if dx and dy else 1)
            if c<costs.get(nxt,float('inf')):
                costs[nxt]=c;parent[nxt]=node;heapq.heappush(heap,(c,nxt))
    if found is None:raise RuntimeError('No off-pad escape via '+str(start))
    nodes=[found]
    while nodes[-1]!=s:nodes.append(parent[nodes[-1]])
    nodes.reverse();pts=[(float(xs[x]),float(ys[y]))for x,y in nodes]
    compact=[pts[0]];i=0
    while i<len(pts)-1:
        j=len(pts)-1
        while j>i+1 and fblocked.intersects(LineString([pts[i],pts[j]])):j-=1
        compact.append(pts[j]);i=j
    assert all(not fblocked.intersects(LineString([a,z]))for a,z in zip(compact,compact[1:]))
    addvia(ref,net,compact[-1],diameter,drill);direct(net,compact,neck,layer)
    print('Bent escape via',ref,compact[-1],flush=True)
def pos(pd):return p.ToMM(pd.GetPosition().x),p.ToMM(pd.GetPosition().y)
def polygons(pd,layer):
    q=pd.GetEffectivePolygon(layer);out=[]
    for k in range(q.OutlineCount()):
        ch=q.COutline(k);points=[(p.ToMM(ch.CPoint(i).x),p.ToMM(ch.CPoint(i).y))for i in range(ch.PointCount())]
        if len(points)>=3:out.append(Polygon(points))
    if pd.GetAttribute()==p.PAD_ATTRIB_NPTH and pd.GetDrillSize().x:
        out=[Point(pos(pd)).buffer(p.ToMM(pd.GetDrillSize().x)/2+.05)]
    return out
def route(start,end,layer=p.F_Cu,width=.2,step=.025,bounds=(30,1,52,18)):
    a,z=pad(*start),pad(*end);net=a.GetNetname();assert net==z.GetNetname();src,goal=pos(a),pos(z)
    obstacles=[];clearance=.205+width/2
    for fp in board.GetFootprints():
        for pd in fp.Pads():
            if pd.GetNetname()!=net and pd.IsOnLayer(layer):obstacles.extend(sh.buffer(clearance)for sh in polygons(pd,layer))
    for t in board.GetTracks():
        if t.GetNetname()==net:continue
        if isinstance(t,p.PCB_VIA):obstacles.append(Point(pos(t)).buffer(p.ToMM(t.GetWidth(layer))/2+clearance))
        elif t.GetLayer()==layer:
            aa,zz=t.GetStart(),t.GetEnd()
            obstacles.append(LineString([(p.ToMM(aa.x),p.ToMM(aa.y)),(p.ToMM(zz.x),p.ToMM(zz.y))]).buffer(p.ToMM(t.GetWidth())/2+clearance))
    obstacle=unary_union(obstacles)
    x0=src[0]+math.floor((bounds[0]-src[0])/step)*step;y0=src[1]+math.floor((bounds[1]-src[1])/step)*step
    nx=math.ceil((bounds[2]-x0)/step)+1;ny=math.ceil((bounds[3]-y0)/step)+1
    xs=x0+np.arange(nx)*step;ys=y0+np.arange(ny)*step
    xx,yy=np.meshgrid(xs,ys);blocked=contains_xy(obstacle,xx,yy)
    s=(round((src[0]-x0)/step),round((src[1]-y0)/step));g=(round((goal[0]-x0)/step),round((goal[1]-y0)/step))
    if blocked[s[1],s[0]] or blocked[g[1],g[0]]:raise RuntimeError('Endpoint blocked: '+net+' '+str((bool(blocked[s[1],s[0]]),bool(blocked[g[1],g[0]]))))
    costs={s:0};parent={};heap=[(math.dist(s,g),0,s)];found=False
    while heap:
        _,cost,node=heapq.heappop(heap)
        if cost!=costs.get(node):continue
        if node==g:found=True;break
        x,y=node
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]:
            xx,yy=x+dx,y+dy
            if not(0<=xx<nx and 0<=yy<ny)or blocked[yy,xx]:continue
            if dx and dy and(blocked[y,xx]or blocked[yy,x]):continue
            # A point-only occupancy grid can miss a narrow obstacle crossing
            # an edge. Check every candidate edge, including off-grid goals.
            edge_a=src if node==s else (float(xs[x]),float(ys[y]))
            edge_z=goal if (xx,yy)==g else (float(xs[xx]),float(ys[yy]))
            if obstacle.intersects(LineString([edge_a,edge_z])):continue
            nxt=(xx,yy);c=cost+(math.sqrt(2)if dx and dy else 1)
            if c<costs.get(nxt,float('inf')):
                costs[nxt]=c;parent[nxt]=node;heapq.heappush(heap,(c+math.dist(nxt,g),c,nxt))
    if not found:
        np.savez('build/route-debug.npz',blocked=blocked,visited=np.array(list(costs)),s=s,g=g,x0=x0,y0=y0,step=step)
        print('No path',net,'visited',len(costs),'source',s,'goal',g,'bbox',tuple(np.array(list(costs)).min(axis=0)),tuple(np.array(list(costs)).max(axis=0)),flush=True)
        raise RuntimeError('No collision-free path '+net)
    nodes=[g]
    while nodes[-1]!=s:nodes.append(parent[nodes[-1]])
    nodes.reverse();points=[src]+[(xs[x],ys[y])for x,y in nodes[1:-1]]+[goal]
    # Greedy visibility compression keeps exact geometric clearance checks.
    compact=[points[0]];i=0
    while i<len(points)-1:
        j=len(points)-1
        while j>i+1 and obstacle.intersects(LineString([points[i],points[j]])):j-=1
        compact.append(points[j]);i=j
    for aa,zz in zip(compact,compact[1:]):
        if math.dist(aa,zz)<1e-6:continue
        assert not obstacle.intersects(LineString([aa,zz])),net
        t=p.PCB_TRACK(board);t.SetStart(p.VECTOR2I(p.FromMM(float(aa[0])),p.FromMM(float(aa[1]))));t.SetEnd(p.VECTOR2I(p.FromMM(float(zz[0])),p.FromMM(float(zz[1]))));t.SetWidth(p.FromMM(width));t.SetLayer(layer);t.SetNetCode(a.GetNetCode());board.Add(t)
    print(net,'routed',len(compact)-1,'segments',round(sum(math.dist(x,y)for x,y in zip(compact,compact[1:])),3),'mm',flush=True)
