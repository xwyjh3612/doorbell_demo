"""Connect actual ground copper components, including through-via links.

Native zone reports use the zone origin instead of the isolated lobe position.
This script derives the real disconnected copper graph and routes at its edges.
It never removes required ground pads or suppresses native unconnected checks.
"""
from pathlib import Path
import json,math
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
scope={'__file__':str(ROOT/'connect_two_layers.py')}
prefix=(ROOT/'connect_two_layers.py').read_text(encoding='utf8').split("d=json.loads")[0]
exec(compile(prefix,'two_layer_loader','exec'),scope)
r=scope['r'];m=scope['m'];b=r.board
from shapely.geometry import Point,Polygon,LineString
from shapely.ops import unary_union,nearest_points
layers=[p.F_Cu,p.B_Cu];report=[]
def ring(ch):return [(p.ToMM(ch.CPoint(i).x),p.ToMM(ch.CPoint(i).y))for i in range(ch.PointCount())]
def graph():
    shapes={li:[]for li in layers}
    for z in b.Zones():
        if z.GetNetname()!='GND':continue
        q=z.GetFilledPolysList(z.GetLayer())
        for i in range(q.OutlineCount()):
            sh=Polygon(ring(q.COutline(i)),[ring(q.CHole(i,j))for j in range(q.HoleCount(i))]).buffer(0)
            if not sh.is_empty:shapes[z.GetLayer()].append(sh)
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            if pd.GetNetname()!='GND':continue
            for li in layers:
                if pd.IsOnLayer(li):shapes[li]+=r.polygons(pd,li)
    vias=[]
    for t in b.GetTracks():
        if t.GetNetname()!='GND':continue
        if isinstance(t,p.PCB_VIA):
            vias.append(r.pos(t))
            for li in layers:shapes[li].append(Point(r.pos(t)).buffer(p.ToMM(t.GetWidth(li))/2))
        else:
            a,z=t.GetStart(),t.GetEnd();shapes[t.GetLayer()].append(LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]).buffer(p.ToMM(t.GetWidth())/2))
    nodes=[]
    for li in layers:
        whole=unary_union(shapes[li]);pieces=list(whole.geoms)if hasattr(whole,'geoms')else[whole]
        nodes += [(li,sh)for sh in pieces if sh.area>.0001]
    parent=list(range(len(nodes)))
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    plated=[r.pos(pd)for fp in b.GetFootprints()for pd in fp.Pads()if pd.GetNetname()=='GND'and pd.GetAttribute()==p.PAD_ATTRIB_PTH]
    for xy in [*vias,*plated]:
        hit=[i for i,(_,sh)in enumerate(nodes)if sh.intersects(Point(xy))]
        for i in hit[1:]:parent[find(i)]=find(hit[0])
    groups={}
    for i in range(len(nodes)):groups.setdefault(find(i),[]).append(i)
    return nodes,sorted(groups.values(),key=lambda ids:-sum(nodes[i][1].area for i in ids))
for iteration in range(25):
    nodes,groups=graph()
    print('Ground copper components:',len(groups),flush=True)
    if len(groups)<=1:break
    main=groups[0];candidates=[]
    for group in groups[1:]:
        for i in group:
            for j in main:
                li,sh=nodes[i];lj,target=nodes[j]
                inner=sh.buffer(-.12);inner=sh if inner.is_empty else inner
                other=target.buffer(-.12);other=target if other.is_empty else other
                a,z=nearest_points(inner,other)
                candidates.append((a.distance(z)+(0 if li==lj else 1),i,j,(a.x,a.y),(z.x,z.y)))
    connected=False
    for distance,i,j,src,goal in sorted(candidates)[:20]:
        li,lj=nodes[i][0],nodes[j][0]
        av='GC_A_'+str(iteration);zv='GC_Z_'+str(iteration)
        r.virtual[av]=r.Endpoint('GND',src);r.virtual[zv]=r.Endpoint('GND',goal)
        r.virtual[av].IsOnLayer=lambda layer,used=li:layer==used
        r.virtual[zv].IsOnLayer=lambda layer,used=lj:layer==used
        bounds=(max(.5,min(src[0],goal[0])-4),max(.5,min(src[1],goal[1])-4),min(99.5,max(src[0],goal[0])+4),min(74.5,max(src[1],goal[1])+4))
        try:
            result=m.route(r,(av,0),(zv,0),width=.2,step=.05,bounds=bounds)
            report.append({'from_mm':src,'to_mm':goal,**result});connected=True;p.SaveBoard(str(file),b);break
        except RuntimeError:continue
    if not connected:break
p.SaveBoard(str(file),b)
nodes,groups=graph()
(ROOT/'exports/ground-component-links.json').write_text(json.dumps({'added_connections':report,'geometric_components_remaining':len(groups),'requires_native_DRC':True},indent=2)+'\n',encoding='utf8')
print('Ground component connections:',len(report),'remaining:',len(groups))
