"""Shorten continuous low-speed routes; keep pads, vias and branch taps fixed.

Works in an isolated copy. It does not redesign USB, RF or switch-node copper.
Native DRC/parity is required after the geometric obstacle checks.
"""
import collections, hashlib, json, math, shutil, sys
from pathlib import Path
import pcbnew as p
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO/'build/cad-tools/route-python'))
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

OUT = REPO/'build/v7-back-routes-20261124'
OUT.mkdir(parents=True, exist_ok=True)
FILE = OUT/'voice_mainboard_v7.kicad_pcb'
BASE = ROOT/'voice_mainboard_v7.kicad_pcb'
for name in ['voice_mainboard_v7.kicad_pcb', 'voice_mainboard_v7.kicad_sch', 'voice_mainboard_v7.kicad_pro', 'voice_mainboard_v7.kicad_dru', 'VoiceV2.kicad_sym', 'fp-lib-table', 'sym-lib-table']:
    shutil.copy2(ROOT/name, OUT/name)
shutil.copytree(ROOT/'VoiceV2.pretty', OUT/'VoiceV2.pretty', dirs_exist_ok=True)
b = p.LoadBoard(str(FILE))
held = []
def xy(v): return (p.ToMM(v.x), p.ToMM(v.y))
def key(v): return (v.x, v.y)
def uid(t): return t.m_Uuid.AsString()
def pad_shapes(pd, layer):
    poly = pd.GetEffectivePolygon(layer)
    result = []
    for i in range(poly.OutlineCount()):
        ring = poly.COutline(i)
        pts = [xy(ring.CPoint(j)) for j in range(ring.PointCount())]
        if len(pts) >= 3: result.append(Polygon(pts))
    if pd.GetAttribute() == p.PAD_ATTRIB_NPTH and pd.GetDrillSize().x:
        result = [Point(xy(pd.GetPosition())).buffer(p.ToMM(pd.GetDrillSize().x)/2+.05)]
    return result
def stats():
    out = {}
    for layer in [p.F_Cu, p.B_Cu]:
        tracks = [t for t in b.GetTracks() if not isinstance(t,p.PCB_VIA) and t.GetLayer()==layer]
        joints = collections.defaultdict(list)
        for t in tracks:
            for v in [t.GetStart(),t.GetEnd()]: joints[(t.GetNetname(),*key(v))].append(t)
        bends = 0
        for items in joints.values():
            if len(items)!=2: continue
            a,z = items
            av = a.GetEnd()-a.GetStart(); zv = z.GetEnd()-z.GetStart()
            if av.x*zv.y!=av.y*zv.x: bends+=1
        out[b.GetLayerName(layer)] = {'segments':len(tracks),'degree_two_turns':bends,'track_length_mm':round(sum(p.ToMM(t.GetLength()) for t in tracks),3)}
    out['vias'] = sum(isinstance(t,p.PCB_VIA) for t in b.GetTracks())
    return out

before = stats()
excluded = {'GND','CELL_NEG','VIN_FUSED','RF_ANT','RF_FEED','M_USB_DP','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19','SERVICE_USB_DP','SERVICE_USB_DM','BUCK_SW','UPS_SW','ESP_SW'}
obstacles = {}; trees = {}; fixed = collections.defaultdict(list)
for layer in [p.F_Cu,p.B_Cu]:
    obs=[]
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            if not pd.IsOnLayer(layer): continue
            for sh in pad_shapes(pd,layer):
                obs.append((pd.GetNetname(),None,sh))
                fixed[(pd.GetNetname(),layer)].append(sh.buffer(.000002))
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            sh=Point(xy(t.GetPosition())).buffer(p.ToMM(t.GetWidth(layer))/2)
            obs.append((t.GetNetname(),uid(t),sh))
            fixed[(t.GetNetname(),layer)].append(sh.buffer(.000002))
        elif t.GetLayer()==layer:
            obs.append((t.GetNetname(),uid(t),LineString([xy(t.GetStart()),xy(t.GetEnd())]).buffer(p.ToMM(t.GetWidth())/2)))
    for zone in [*b.Zones(),*[z for fp in b.GetFootprints() for z in fp.Zones()]]:
        if not zone.GetIsRuleArea() or not zone.IsOnLayer(layer):continue
        for i in range(zone.Outline().OutlineCount()):
            ring=zone.Outline().COutline(i)
            obs.append(('__KEEP_OUT__',None,Polygon([xy(ring.CPoint(j)) for j in range(ring.PointCount())])))
    obstacles[layer]=obs; trees[layer]=STRtree([s for n,u,s in obs])
added={p.F_Cu:[],p.B_Cu:[]}; removed=set()

def options(a,z):
    dx,dy=z[0]-a[0],z[1]-a[1]
    sx=1 if dx>=0 else -1; sy=1 if dy>=0 else -1
    d=min(abs(dx),abs(dy))
    opts=[[a,z],[a,(a[0],z[1]),z],[a,(z[0],a[1]),z],
          [a,(a[0]+sx*d,a[1]+sy*d),z],[a,(z[0]-sx*d,z[1]-sy*d),z]]
    # Split remaining axial length equally across both ends for a straight
    # central diagonal; often removes staircases in congested corridors.
    if abs(dx)>=abs(dy):
        extra=(abs(dx)-abs(dy))/2
        opts.append([a,(a[0]+sx*extra,a[1]),(z[0]-sx*extra,z[1]),z])
    else:
        extra=(abs(dy)-abs(dx))/2
        opts.append([a,(a[0],a[1]+sy*extra),(z[0],z[1]-sy*extra),z])
    for nodes in opts:
        out=[nodes[0]]
        for q in nodes[1:]:
            q=(round(q[0],6),round(q[1],6))
            if math.dist(out[-1],q)>.000001:out.append(q)
        if any(min(abs(x[0]-y[0]),abs(x[1]-y[1]))>.000002 and abs(abs(x[0]-y[0])-abs(x[1]-y[1]))>.000002 for x,y in zip(out,out[1:])):continue
        yield out

def clear(nodes,net,layer,width):
    line=LineString(nodes); gap=width/2+.205
    # Edges, mounting holes and antenna keepouts stay clear.
    if any(not (.8<=x<=99.2 and .8<=y<=74.2) for x,y in nodes): return False
    for i in trees[layer].query(line.buffer(gap)):
        n,u,sh=obstacles[layer][i]
        if n==net or u in removed:continue
        if sh.distance(line)<=gap:return False
    return not any(n!=net and sh.distance(line)<=gap for n,sh in added[layer])

def chains():
    groups=collections.defaultdict(list)
    for t in b.GetTracks():
        if not isinstance(t,p.PCB_VIA) and t.GetNetname() not in excluded:
            groups[(t.GetNetname(),t.GetLayer(),t.GetWidth())].append(t)
    result=[]
    for (net,layer,width),tracks in groups.items():
        joints=collections.defaultdict(list)
        for t in tracks:
            for q in [t.GetStart(),t.GetEnd()]: joints[key(q)].append(t)
        anchors=set()
        # Keep every pad/via contact, including contacts in the middle of an
        # existing segment. Preserve endpoints around same-net crossing taps.
        lines=[LineString([xy(t.GetStart()),xy(t.GetEnd())]) for t in tracks]
        tree=STRtree(lines)
        for i,t in enumerate(tracks):
            a,z=key(t.GetStart()),key(t.GetEnd())
            line=lines[i]
            if any(sh.intersects(line) for sh in fixed[(net,layer)]): anchors.update([a,z])
            for j in tree.query(line):
                if i==j:continue
                other=tracks[j]
                if {a,z} & {key(other.GetStart()),key(other.GetEnd())}:continue
                if line.intersects(lines[j]):anchors.update([a,z])
        for point,items in joints.items():
            if len(items)!=2:anchors.add(point)
        used=set()
        for start in sorted(anchors):
            for t in joints[start]:
                if uid(t) in used:continue
                items=[];nodes=[(p.ToMM(start[0]),p.ToMM(start[1]))];current=start
                while uid(t) not in used:
                    used.add(uid(t));items.append(t)
                    nxt=key(t.GetEnd()) if key(t.GetStart())==current else key(t.GetStart())
                    nodes.append((p.ToMM(nxt[0]),p.ToMM(nxt[1])))
                    if nxt in anchors:break
                    t=next(tt for tt in joints[nxt] if uid(tt) not in used)
                    current=nxt
                if len(items)>2: result.append((net,layer,width,items,nodes))
    return sorted(result,key=lambda item:len(item[3]),reverse=True)

initial=chains()
(OUT/'chain-audit.json').write_text(json.dumps({'before':before,'chains':[{'net':n,'layer':b.GetLayerName(l),'segments':len(ts),'length_mm':sum(math.dist(a,z)for a,z in zip(pts,pts[1:])),'nodes':pts}for n,l,w,ts,pts in initial]},indent=2),encoding='utf-8')
if '--audit' in sys.argv:
    print(json.dumps({'before':before,'longest':json.loads((OUT/'chain-audit.json').read_text())['chains'][:15]},indent=2));sys.exit()

changes=[]
for passno in range(2):
    for net,layer,width_i,tracks,nodes in chains():
        width=p.ToMM(width_i);count=len(nodes)
        # Dynamic programming over existing waypoints with electrically fixed
        # endpoints. A shortcut must reduce both length and route complexity.
        costs=[float('inf')]*count;costs[-1]=0;lengths=[0.]*count;paths=[None]*count
        for i in range(count-2,-1,-1):
            segment=[nodes[i],nodes[i+1]]
            lengths[i]=math.dist(*segment)+lengths[i+1]
            costs[i]=math.dist(*segment)+.5+costs[i+1];paths[i]=(i+1,segment)
            for j in range(i+2,count):
                oldlen=sum(math.dist(a,z) for a,z in zip(nodes[i:j],nodes[i+1:j+1]))
                for candidate in options(nodes[i],nodes[j]):
                    newlen=sum(math.dist(a,z) for a,z in zip(candidate,candidate[1:]))
                    if newlen>oldlen+.000002 or len(candidate)-1>=j-i:continue
                    score=newlen+.5*(len(candidate)-1)+costs[j]
                    if score>=costs[i]-.000002 or not clear(candidate,net,layer,width):continue
                    costs[i]=score;paths[i]=(j,candidate)
        revised=[nodes[0]];i=0
        while i<count-1:
            j,path=paths[i];revised.extend(path[1:]);i=j
        oldlen=sum(math.dist(a,z) for a,z in zip(nodes,nodes[1:]));newlen=sum(math.dist(a,z)for a,z in zip(revised,revised[1:]))
        if len(revised)>=count or newlen>oldlen+.00001:continue
        for t in tracks:removed.add(uid(t));held.append(t);b.Remove(t)
        for a,z in zip(revised,revised[1:]):
            t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])));t.SetEnd(p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1])));t.SetWidth(width_i);t.SetLayer(layer);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
            added[layer].append((net,LineString([a,z]).buffer(width/2)))
        changes.append({'net':net,'layer':b.GetLayerName(layer),'old_segments':len(tracks),'new_segments':len(revised)-1,'old_length_mm':round(oldlen,6),'new_length_mm':round(newlen,6),'old_nodes':nodes,'new_nodes':revised})
        print(net,b.GetLayerName(layer),len(tracks),'->',len(revised)-1,round(oldlen-newlen,3),'mm saved',flush=True)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
report={'date':'2026-11-24','base_sha256':hashlib.sha256(BASE.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'before':before,'after':stats(),'changes':changes,'excluded_nets':sorted(excluded),'placement_changed':False,'manufacturing_ready':False,'verification':'Geometric screening only; native DRC/parity required.'}
(OUT/'route-changes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for t in held:t.thisown=False
print(json.dumps({k:v for k,v in report.items()if k!='changes'},ensure_ascii=False,indent=2))
