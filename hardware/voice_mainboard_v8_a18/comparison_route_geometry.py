"""Repair specific native DRC airwires with geometric two-layer searches.

Preserves pad nets and checks copper/holes/rule-area obstacles. Changes still
require a fresh independent KiCad DRC. No DRC exclusions are generated here.
"""
from pathlib import Path
import heapq, json, math, re, sys, time, types, os, fnmatch
import pcbnew as p
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO/'build/cad-tools/route-python'))
import numpy as np
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import unary_union
from shapely import contains_xy

FILE = Path(os.environ['A18_REPAIR_BOARD']).resolve(); ROOT=FILE.parent
b = p.LoadBoard(str(FILE))
settings_manager=p.GetSettingsManager()
assert settings_manager.LoadProject(str(FILE.with_suffix('.kicad_pro')))
b.SetProject(settings_manager.GetProject(str(FILE.with_suffix('.kicad_pro'))))
# Bind the actual project's rules without resetting any verified copper sizes.
b.SynchronizeNetsAndNetClasses(False)
project_settings=json.loads(FILE.with_suffix('.kicad_pro').read_text(encoding='utf-8'))
net_classes={q['name']:q['clearance'] for q in project_settings['net_settings']['classes']}
net_patterns=project_settings['net_settings'].get('netclass_patterns',[])
def net_clearance(net):
    return next((net_classes[q['netclass']] for q in net_patterns if fnmatch.fnmatchcase(net,q['pattern'])),net_classes['Default'])
def required_clearance(net,other):
    guard=float(os.environ.get('A18_ROUTE_CLEARANCE_GUARD_MM','.001'))
    # The optional sub-IU tolerance only addresses closed-polygon boundary
    # contact in trial planning. Saved copper is still accepted solely by
    # native DRC under the unchanged project rules (1 IU = 0.000001 mm).
    assert guard>=-.0000001
    return max(net_clearance(net),net_clearance(other))+guard
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
layers=[p.F_Cu,p.B_Cu] if b.GetCopperLayerCount()==2 else [p.F_Cu,p.In1_Cu,p.In2_Cu,p.B_Cu]
def route(net,src,goal,source_layers,goal_layers,width=.2,step=.1,bounds=None,avoidance=()):
    obstacles=[[]for _ in layers];vias=[];reuse=[]
    ripup=os.environ.get('A18_ROUTE_RIPUP_SIGNAL_WIRES')=='1'
    rip_via_nets=set(filter(None,os.environ.get('A18_ROUTE_RIPUP_VIA_NETS','').split(',')))
    protected_nets={'GND','VIN_DC','VIN_FUSED','VIN_PROTECTED','SYS_5V','MODEM_3V8','BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','UPS_SW','BUCK_SW','ESP_SW','ESP_3V3','MODEM_1V8','SPK_PLUS','SPK_MINUS','RF_ANT','RF_FEED'}
    protected_nets.update(filter(None,os.environ.get('A18_RIPUP_PROTECTED_NETS','').split(',')))
    rip_tracks=[];rip_vias=[];rip_masks=[[]for _ in layers]
    via_diameter=float(os.environ.get('A18_ROUTE_VIA_DIAMETER_MM','.45'))
    via_drill=float(os.environ.get('A18_ROUTE_VIA_DRILL_MM','.2'))
    assert via_diameter>=via_drill+.2,'Keep at least 0.1mm annular ring'
    minima=project_settings['board']['design_settings']['rules']
    assert via_diameter>=minima['min_via_diameter'],'Keep the project minimum via diameter'
    assert via_drill>=minima['min_through_hole_diameter'],'Keep the project minimum drill'
    assert width>=minima['min_track_width'],'Keep the project minimum track width'
    for f in b.GetFootprints():
        for d in f.Pads():
            for li,layer in enumerate(layers):
                if not d.IsOnLayer(layer):continue
                for sh in polys(d,layer):
                    margin=required_clearance(net,d.GetNetname())
                    if d.GetNetname()!=net:obstacles[li].append(sh.buffer(margin+width/2))
                    # Conventional off-pad vias, including same-net SMT pads.
                    vias.append(sh.buffer(via_diameter/2+.05 if d.GetNetname()==net else via_diameter/2+margin+.004))
            if d.GetDrillSize().x:
                # Hole-edge separation is 0.25 mm in this project's rules.
                # Include both actual drill radii plus a 0.005 mm guard;
                # the old fixed 0.555 mm inflated this by 0.20 mm for a
                # 0.20 mm via and unnecessarily sealed dense escape paths.
                # Copper-pad clearance is checked separately above, and
                # native KiCad still checks plated slots and NPTH geometry.
                hole=Point(pos(d)).buffer(p.ToMM(d.GetDrillSize().x)/2+via_drill/2+.255)
                vias.append(hole)
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            sh=Point(pos(t));radius=p.ToMM(t.GetWidth(p.F_Cu))/2
            if ripup and not t.IsLocked() and t.GetNetname()!=net and t.GetNetname() not in protected_nets and t.GetNetname() in rip_via_nets:
                rip_vias.append((t,sh,radius))
                for li in range(len(layers)):
                    rip_masks[li].append(sh.buffer(radius+required_clearance(net,t.GetNetname())+width/2))
                continue
            vias.append(sh.buffer(p.ToMM(t.GetDrill())/2+via_drill/2+.255))
            if t.GetNetname()==net:
                if p.ToMM(t.GetWidth(p.F_Cu))>=via_diameter-.001:
                    reuse.append(sh.buffer(max(.075,radius-.04)))
                continue
            margin=required_clearance(net,t.GetNetname())
            for li in range(len(layers)):obstacles[li].append(sh.buffer(radius+margin+width/2))
            vias.append(sh.buffer(radius+via_diameter/2+margin+.004))
        else:
            if t.GetNetname()==net:continue
            a,z=t.GetStart(),t.GetEnd()
            sh=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))])
            radius=p.ToMM(t.GetWidth())/2
            margin=required_clearance(net,t.GetNetname())
            if ripup and not t.IsLocked() and t.GetNetname() not in protected_nets:
                rip_tracks.append((t,sh.buffer(radius),t.GetLayer()))
                rip_masks[layers.index(t.GetLayer())].append(sh.buffer(radius+margin+width/2))
            else:
                obstacles[layers.index(t.GetLayer())].append(sh.buffer(radius+margin+width/2))
            vias.append(sh.buffer(radius+via_diameter/2+margin+.004))
    for z,sh in rules:
        for li,layer in enumerate(layers):
            if z.IsOnLayer(layer)and z.GetDoNotAllowTracks():obstacles[li].append(sh.buffer(width/2+.011))
        if z.GetDoNotAllowVias():vias.append(sh.buffer(via_diameter/2+.011))
    for li,xy,radius in avoidance:obstacles[li].append(Point(xy).buffer(radius))
    obstacles=[unary_union(x)for x in obstacles]
    rip_masks=[unary_union(x)for x in rip_masks]
    via_obstacle=unary_union(vias);reuse_shape=unary_union(reuse)
    # Each endpoint lies exactly on a grid anchor or uses exact final geometry.
    bounds=(.5,.5,72.5,72.5)if bounds is None else bounds
    x0=src[0]+math.floor((bounds[0]-src[0])/step)*step;y0=src[1]+math.floor((bounds[1]-src[1])/step)*step
    xs=x0+np.arange(math.ceil((bounds[2]-x0)/step)+1)*step
    ys=y0+np.arange(math.ceil((bounds[3]-y0)/step)+1)*step
    xx,yy=np.meshgrid(xs,ys)
    grids=[contains_xy(o,xx,yy)|~contains_xy(outline.buffer(-width/2-.501),xx,yy)for o in obstacles]
    via_grid=contains_xy(via_obstacle,xx,yy)|~contains_xy(outline.buffer(-via_diameter/2-.5),xx,yy)
    reuse_grid=contains_xy(reuse_shape,xx,yy)
    rip_grids=[contains_xy(o,xx,yy)for o in rip_masks]if ripup else None
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
    deadline=time.monotonic()+float(os.environ.get('A18_ROUTE_TIME_LIMIT_SECONDS','45'))
    visited=0
    native_nodes=None
    if os.environ.get('A18_ROUTE_NATIVE_GRID')=='1':
        from native_grid_search import search
        native_nodes,visited,native_reachable=search(grids,via_grid,reuse_grid,rip_grids,sx,sy,gx,gy,source_layers,goal_nodes)
        heap=[]
        if native_nodes:found=native_nodes[-1]
    while heap:
        _,cost,node=heapq.heappop(heap)
        if cost!=costs.get(node):continue
        visited+=1
        if visited%2000==0 and time.monotonic()>deadline:raise RuntimeError('search time limit')
        x,y,li=node
        if node in goal_nodes:found=node;break
        candidates=[(x+dx,y+dy,li,cost+(math.sqrt(2)if dx and dy else 1))
                    for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]]
        if reuse_grid[y,x]or not via_grid[y,x]:
            candidates.extend((x,y,k,cost+(5 if reuse_grid[y,x]else float(os.environ.get('A18_ROUTE_VIA_COST','18')))) for k in range(len(layers)) if k!=li)
        for tx,ty,k,newcost in candidates:
            if not(0<=tx<len(xs)and 0<=ty<len(ys))or grids[k][ty,tx]:continue
            if k==li and tx!=x and ty!=y and(grids[k][y,tx]or grids[k][ty,x]):continue
            nxt=(tx,ty,k)
            if ripup and rip_grids[k][ty,tx]:newcost+=float(os.environ.get('A18_RIPUP_CROSSING_COST','10'))
            if newcost<costs.get(nxt,float('inf')):
                costs[nxt]=newcost;parent[nxt]=node
                heapq.heappush(heap,(newcost+math.hypot(tx-gx,ty-gy),newcost,nxt))
    if found is None:
        if os.environ.get('A18_ROUTE_DIAGNOSTIC_FILE'):
            reachable=native_reachable if native_nodes is not None else np.zeros((len(layers),len(ys),len(xs)),dtype=bool)
            if native_nodes is None:
                for x,y,li in costs:reachable[li,y,x]=True
            np.savez_compressed(os.environ['A18_ROUTE_DIAGNOSTIC_FILE'],xs=xs,ys=ys,
                                grids=np.stack(grids),via_blocked=via_grid,via_reuse=reuse_grid,
                                reachable=reachable,src=np.array(src),goal=np.array(goal))
        raise RuntimeError('no clear route; visited='+str(visited)+' source blocked='+str([bool(grids[li][sy,sx])for li in source_layers])+' reachable goal anchors='+str(len(goal_nodes)))
    nodes=native_nodes if native_nodes is not None else [found]
    if native_nodes is None:
        while nodes[-1]in parent:nodes.append(parent[nodes[-1]])
        nodes.reverse()
    groups=[];current=[src];li=nodes[0][2];newvias=[]
    for x,y,k in nodes[1:]:
        xy=(float(xs[x]),float(ys[y]))
        if k!=li:
            groups.append((li,current))
            if not reuse_shape.intersects(Point(xy)):newvias.append(xy)
            current=[xy];li=k
        else:current.append(xy)
    if math.dist(current[-1],goal)>1e-8:current.append(goal)
    groups.append((li,current));segments=[]
    safe_outline=outline.buffer(-width/2-.501)
    def shortcut(a,z,li,allow_rip_crossing):
        # Try conventional 45-degree/orthogonal doglegs as well as a straight
        # segment. Exact floating-point endpoint offsets must not force a
        # long staircase of grid segments. Keep the search's rip-up cost
        # meaningful: a shortcut cannot introduce extra wire crossings.
        dx=z[0]-a[0];dy=z[1]-a[1]
        sx=1 if dx>=0 else -1;sy=1 if dy>=0 else -1
        diagonal=min(abs(dx),abs(dy))
        choices=[]
        if min(abs(dx),abs(dy))<1e-6 or abs(abs(dx)-abs(dy))<1e-6:
            choices.append([a,z])
        choices.extend([[a,(a[0]+sx*diagonal,a[1]+sy*diagonal),z],
                        [a,(z[0]-sx*diagonal,z[1]-sy*diagonal),z],
                        [a,(z[0],a[1]),z],[a,(a[0],z[1]),z]])
        for choice in choices:
            choice=[q for i,q in enumerate(choice) if i==0 or math.dist(choice[i-1],q)>1e-7]
            if all(not obstacles[li].intersects(LineString([u,v]))
                   and safe_outline.covers(LineString([u,v]))
                   and (allow_rip_crossing or not rip_masks[li].intersects(LineString([u,v])))
                   for u,v in zip(choice,choice[1:])):
                return choice
        return None
    for li,points in groups:
        compact=[points[0]];i=0
        while i<len(points)-1:
            j=len(points)-1
            # Preserve ordinary horizontal/vertical/45-degree routing. Any
            # shortcut must remain within the actual notched board outline.
            while j>i:
                choice=shortcut(points[i],points[j],li,ripup and j==i+1)
                if choice:break
                line=LineString([points[i],points[j]])
                if j==i+1 and not obstacles[li].intersects(line) and safe_outline.covers(line):
                    choice=[points[i],points[j]];break
                # Bounded sampling avoids quadratic geometry work on long
                # congested paths. It only retains extra safe grid corners;
                # every emitted edge still passes the exact same clearance
                # and outline checks, including the adjacent-edge fallback.
                if os.environ.get('A18_ROUTE_FAST_COMPACT')=='1':
                    j-=max(1,(j-i)//16)
                else:
                    j-=1
            if j==i:
                # Grid endpoints can both be clear while a short edge clips a
                # curved copper obstacle. Re-plan around that exact failed
                # edge before adding any copper, keeping physical clearance.
                if len(avoidance)<8:
                    middle=((points[i][0]+points[i+1][0])/2,(points[i][1]+points[i+1][1])/2)
                    return route(net,src,goal,source_layers,goal_layers,width,step,bounds,[*avoidance,(li,middle,step*.75)])
                raise RuntimeError('exact clearance failed after conservative replans: '+str(points[i:i+2]))
            compact.extend(choice[1:]);i=j
        segments.extend((layers[li],a,z)for a,z in zip(compact,compact[1:])if math.dist(a,z)>1e-6)
    # Retain the exact planned path while combining consecutive collinear
    # grid steps. This cannot introduce a shortcut across another obstacle.
    merged=[]
    for layer,a,z in segments:
        if merged and merged[-1][0]==layer and math.dist(merged[-1][2],a)<1e-7:
            old_layer,old_a,old_z=merged[-1]
            v=(old_z[0]-old_a[0],old_z[1]-old_a[1]);w=(z[0]-a[0],z[1]-a[1])
            if abs(v[0]*w[1]-v[1]*w[0])<1e-8 and v[0]*w[0]+v[1]*w[1]>0:
                merged[-1]=(layer,old_a,z);continue
        merged.append((layer,a,z))
    segments=merged
    retired=[];held=[]
    if ripup:
        for t,sh,layer in rip_tracks:
            if any(sl==layer and sh.buffer(width/2+required_clearance(net,t.GetNetname())).intersects(LineString([a,z]))for sl,a,z in segments):
                retired.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});held.append(t);b.Remove(t)
        for t,sh,radius in rip_vias:
            clearance=required_clearance(net,t.GetNetname())
            drill_spacing=(p.ToMM(t.GetDrill())+via_drill)/2+.255
            if (any(sh.distance(LineString([a,z]))<radius+width/2+clearance for _,a,z in segments)
                or any(sh.distance(Point(xy))<max(drill_spacing,radius+via_diameter/2+clearance+.004) for xy in newvias)):
                retired.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});held.append(t);b.Remove(t)
    for layer,a,z in segments:
        t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])))
        t.SetEnd(p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1])));t.SetWidth(p.FromMM(width));t.SetLayer(layer)
        t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
        if os.environ.get('A18_LOCK_REPAIRS')=='1':t.SetLocked(True)
    for xy in newvias:
        t=p.PCB_VIA(b);t.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
        t.SetWidth(p.FromMM(via_diameter));t.SetDrill(p.FromMM(via_drill));t.SetViaType(p.VIATYPE_THROUGH)
        t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
        if os.environ.get('A18_LOCK_REPAIRS')=='1':t.SetLocked(True)
    for t in held:t.thisown=False
    return {'segments':len(segments),'new_vias':len(newvias),'retired_signal_wires':retired}

def item_index():
    return {str(x.m_Uuid.AsString()):x for x in [*[d for f in b.GetFootprints()for d in f.Pads()],*b.GetTracks(),*b.Zones()]}
if __name__=='__main__':
    drc=Path(sys.argv[1]);report=json.loads(drc.read_text(encoding='utf-8'));items=item_index();changes=[]
    for error in report['unconnected_items']:
        a,z=error['items'];ea=items.get(a['uuid']);ez=items.get(z['uuid'])
        if ea is None or ez is None or isinstance(ea,p.ZONE)or isinstance(ez,p.ZONE):continue
        net=ea.GetNetname();assert net==ez.GetNetname()
        selected_nets=set(filter(None,os.environ.get('A18_ONLY_NETS','').split(',')))
        if selected_nets and net not in selected_nets:continue
        src=(a['pos']['x'],a['pos']['y']);goal=(z['pos']['x'],z['pos']['y'])
        sl={i for i,l in enumerate(layers)if ea.IsOnLayer(l)};gl={i for i,l in enumerate(layers)if ez.IsOnLayer(l)}
        start=time.monotonic();entry={'net':net,'from':src,'to':goal}
        default_width=.5 if net in ['VIN_DC','VIN_FUSED'] else (.25 if net in ['SYS_5V','BAT_BOOST_5V','MODEM_3V8','VIN_PROTECTED','ESP_3V3'] else .16)
        width=float(os.environ.get('A18_NATIVE_REPAIR_WIDTH',default_width))
        try:entry.update(route(net,src,goal,sl,gl,width=width),success=True,width_mm=width)
        except RuntimeError as e:entry.update(success=False,reason=str(e))
        entry['seconds']=time.monotonic()-start;changes.append(entry)
        p.SaveBoard(str(FILE),b)
        print(net,entry['success'],entry.get('reason',''),round(entry['seconds'],2),flush=True)
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    (ROOT/'exports'/('repairs-'+drc.stem+'.json')).write_text(json.dumps(changes,indent=2),encoding='utf-8')
