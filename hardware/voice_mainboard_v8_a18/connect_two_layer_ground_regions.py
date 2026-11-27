"""Connect stranded filled ground regions through ordinary off-pad vias.

Unlike overlap-only stitching, this can continue from a safe via landing on
one ground island through the opposite face. Preserve all real pad geometry;
native DRC and return-path review remain mandatory.
"""
from pathlib import Path
import collections,json,math,os,time
import pcbnew as p
from comparison_route_geometry import b,FILE,route,pos,polys,rules,layers,required_clearance
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union

def regions():
    result=[]
    for z in b.Zones():
        if z.GetIsRuleArea() or z.GetNetname()!='GND':continue
        shapes=z.GetFilledPolysList(z.GetLayer())
        for i in range(shapes.OutlineCount()):
            q=shapes.COutline(i)
            outer=[(p.ToMM(q.CPoint(j).x),p.ToMM(q.CPoint(j).y))for j in range(q.PointCount())]
            holes=[]
            for k in range(shapes.HoleCount(i)):
                h=shapes.CHole(i,k);holes.append([(p.ToMM(h.CPoint(j).x),p.ToMM(h.CPoint(j).y))for j in range(h.PointCount())])
            sh=Polygon(outer,holes).buffer(0)
            if sh.area>.01:result.append((z.GetLayer(),sh))
    return result

report=[];searches=0;started=time.monotonic()
max_searches=int(os.environ.get('A18_GROUND_MAX_SEARCHES','24'))
for iteration in range(12):
    rs=regions();parent=list(range(len(rs)))
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def join(a,z):parent[find(a)]=find(z)
    existing=[t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND']
    existing += [d for f in b.GetFootprints()for d in f.Pads()if d.GetNetname()=='GND'and d.GetAttribute()==p.PAD_ATTRIB_PTH]
    owners={}
    for t in existing:
        ids=[]
        for i,(layer,sh)in enumerate(rs):
            if not t.IsOnLayer(layer):continue
            copper=[Point(pos(t)).buffer(p.ToMM(t.GetWidth(layer))/2)]if isinstance(t,p.PCB_VIA)else polys(t,layer)
            if any(own.intersects(sh)for own in copper):ids.append(i)
        for i in ids[1:]:join(ids[0],i)
        owners[t.m_Uuid.AsString()]=ids
    groups=collections.defaultdict(list)
    for i in range(len(rs)):groups[find(i)].append(i)
    if len(groups)<2:break
    main=max(groups,key=lambda k:sum(rs[i][1].area for i in groups[k]))
    goals=[t for t in existing if any(find(i)==main for i in owners[t.m_Uuid.AsString()])]
    if not goals:break
    blocked=[]
    for f in b.GetFootprints():
        for d in f.Pads():
            for layer in layers:
                if d.IsOnLayer(layer):blocked.extend(sh.buffer(.275 if d.GetNetname()=='GND'else .225+required_clearance('GND',d.GetNetname()))for sh in polys(d,layer))
            if d.GetDrillSize().x:blocked.append(Point(pos(d)).buffer(p.ToMM(d.GetDrillSize().x)/2+.5))
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            blocked.append(Point(pos(t)).buffer(.5 if t.GetNetname()=='GND'else p.ToMM(t.GetWidth(p.F_Cu))/2+.225+required_clearance('GND',t.GetNetname())))
        elif t.GetNetname()!='GND':
            blocked.append(LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2+.225+required_clearance('GND',t.GetNetname())))
    for z,sh in rules:
        if z.GetDoNotAllowVias():blocked.append(sh.buffer(.236))
    obstacle=unary_union(blocked);success=False
    for group,indices in sorted(groups.items(),key=lambda q:-sum(rs[i][1].area for i in q[1])):
        if group==main:continue
        options=[]
        for i in indices:
            allowed=rs[i][1].buffer(-.236).difference(obstacle)
            pieces=[allowed]if allowed.geom_type=='Polygon'else[q for q in getattr(allowed,'geoms',[])if q.geom_type=='Polygon']
            options.extend((sh.area,sh.representative_point())for sh in pieces if sh.area>.001)
        if not options:continue
        for _,point in sorted(options,key=lambda q:-q[0])[:2]:
            xy=(point.x,point.y)
            via=p.PCB_VIA(b);via.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
            via.SetWidth(p.FromMM(.45));via.SetDrill(p.FromMM(.2));via.SetLayerPair(p.F_Cu,p.B_Cu)
            via.SetViaType(p.VIATYPE_THROUGH);via.SetNetCode(b.FindNet('GND').GetNetCode());b.Add(via)
            for target in sorted(goals,key=lambda t:math.dist(pos(t),xy))[:4]:
                if searches>=max_searches or time.monotonic()-started>240:break
                searches+=1
                try:
                    result=route('GND',xy,pos(target),{0,1},{0,1},width=.2)
                    report.append({'from_mm':xy,'to_mm':pos(target),'ground_groups_before':len(groups),**result});success=True;break
                except RuntimeError:pass
            if not success:b.Remove(via);via.thisown=False
            if success:break
        if success:break
        if searches>=max_searches or time.monotonic()-started>240:break
    if not success:break
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    print('Ground connection added; prior region groups:',len(groups),flush=True)
(FILE.parent/'exports/ground-region-connections.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Ground region connections added:',len(report))
