"""Create an isolated geometry candidate. Original V6 CAD stays untouched.

Selected improvements: simplify arbitrary-angle routes and repair the input
power bottleneck. All candidate changes require fresh native DRC/parity.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import types
import pcbnew as p

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/'build/v6-layout-refinement-20261124/candidate'
OUT.mkdir(parents=True,exist_ok=True)
base=ROOT/'voice_mainboard_v6.kicad_pcb'
sha=hashlib.sha256(base.read_bytes()).hexdigest()
for name in ['voice_mainboard_v6.kicad_pcb','voice_mainboard_v6.kicad_sch','voice_mainboard_v6.kicad_pro','voice_mainboard_v6.kicad_dru','VoiceV2.kicad_sym','fp-lib-table','sym-lib-table']:
    shutil.copy2(ROOT/name,OUT/name)
shutil.copytree(ROOT/'VoiceV2.pretty',OUT/'VoiceV2.pretty',dirs_exist_ok=True)
FILE=OUT/'voice_mainboard_v6.kicad_pcb'
project_file=OUT/'voice_mainboard_v6.kicad_pro'
project=json.loads(project_file.read_text(encoding='utf-8'))
default=project['net_settings']['classes'][0]
for name,width in [('POWER',.8),('RF',.2),('USB_PENDING',.2)]:
    if not any(c['name']==name for c in project['net_settings']['classes']):
        cls=dict(default);cls.update(name=name,track_width=width,priority=len(project['net_settings']['classes']))
        project['net_settings']['classes'].append(cls)
for net in ['BAT_SENSE_IN','BAT_BOOST_5V','CELL_NEG']:
    project['net_settings']['netclass_patterns'].append({'netclass':'POWER','pattern':net})
for net in ['M_USB_DP','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19','SERVICE_USB_DP','SERVICE_USB_DM']:
    project['net_settings']['netclass_patterns'].append({'netclass':'USB_PENDING','pattern':net})
project_file.write_text(json.dumps(project,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# This checks the repaired bottleneck, not RF/USB impedance or every power rail.
(OUT/'voice_mainboard_v6.kicad_dru').write_text('''(version 1)
(rule "Fused input minimum neck width"
  (condition "A.NetName == 'VIN_FUSED'")
  (constraint track_width (min 0.5mm)))
''',encoding='utf-8')

# Reuse exact obstacle geometry, including antenna keepouts. Replace only the
# input path for the source script; do not run integration/rebuild scripts.
source=(ROOT.parent/'voice_mainboard_v3/route_helpers.py').read_text(encoding='utf-8')
source=source.replace('    obstacle=unary_union(obstacles)', '''    for z in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not z.GetIsRuleArea() or not z.IsOnLayer(layer):continue
        for i in range(z.Outline().OutlineCount()):
            ring=z.Outline().COutline(i)
            obstacles.append(Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]).buffer(width/2+.005))
    obstacle=unary_union(obstacles)''')
source=source.replace('    blocked=unary_union(all_obstacles);fblocked=unary_union(front)', '''    for z in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not z.GetIsRuleArea():continue
        for i in range(z.Outline().OutlineCount()):
            ring=z.Outline().COutline(i)
            sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
            all_obstacles.append(sh.buffer(diameter/2+.005))
            if z.IsOnLayer(layer):front.append(sh.buffer(neck/2+.005))
    blocked=unary_union(all_obstacles);fblocked=unary_union(front)''')
sys.argv=[__file__,str(FILE)]
r=types.ModuleType('candidate_router')
exec(compile(source,'candidate_router','exec'),r.__dict__)
b=r.board
held=[]
changes=[]

def coords(point):return (p.ToMM(point.x),p.ToMM(point.y))
def angular_stats(board):
    count=collections.Counter()
    for t in board.GetTracks():
        if isinstance(t,p.PCB_VIA):continue
        a,z=coords(t.GetStart()),coords(t.GetEnd())
        dx,dy=abs(a[0]-z[0]),abs(a[1]-z[1])
        if min(dx,dy)<.00002:count['horizontal_vertical']+=1
        elif abs(dx-dy)<.00002:count['45_degree']+=1
        else:count['arbitrary_angle']+=1
    return dict(count)

before=angular_stats(b)
# Bottom copper now carries the main current instead of the long 0.2mm top line.
for t in list(b.GetTracks()):
    if t.GetNetname()=='VIN_FUSED':held.append(t);b.Remove(t)
r.escapevia('fuse_power',('F1',2),diameter=.8,drill=.4,neck=.6)
r.escapevia('reverse_power',('Q6',3),diameter=.8,drill=.4,neck=.5)
# Allow broad plane copper to go around existing bottom signal obstacles.
zone=p.ZONE(b);zone.SetLayer(p.B_Cu);zone.SetNet(b.FindNet('VIN_FUSED'))
zone.SetLocalClearance(p.FromMM(.2));zone.SetMinThickness(p.FromMM(.25))
zone.SetAssignedPriority(50);zone.SetPadConnection(p.ZONE_CONNECTION_FULL)
zone.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS);zone.Outline().NewOutline()
for x,y in [(18,39),(31,39),(31,51),(18,51)]:zone.Outline().Append(p.FromMM(x),p.FromMM(y))
b.Add(zone)
changes.append({'net':'VIN_FUSED','old_path_length_mm':18.895,'old_width_mm':.2,'new_bottom_pour_rectangle_mm':[18,39,31,51],
                'escape_widths_mm':[.6,.5],'via_diameter_drill_mm':[.8,.4],'current_rating_verified':False})

# Refit arbitrary-angle segments to normal H/V/45 geometry if exact obstacle
# checks allow it. Preserve every original endpoint, layer, net and branch.
from shapely.geometry import LineString,Point,Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
shapes_by_layer={}
for layer in [p.F_Cu,p.B_Cu]:
    shapes=[]
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            if pd.IsOnLayer(layer):
                shapes.extend((pd.GetNetname(),sh) for sh in r.polygons(pd,layer))
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            shapes.append((t.GetNetname(),Point(coords(t.GetPosition())).buffer(p.ToMM(t.GetWidth(layer))/2)))
        elif t.GetLayer()==layer:
            shapes.append((t.GetNetname(),LineString([coords(t.GetStart()),coords(t.GetEnd())]).buffer(p.ToMM(t.GetWidth())/2)))
    for z in [*b.Zones(),*[z for fp in b.GetFootprints() for z in fp.Zones()]]:
        if not z.GetIsRuleArea() or not z.IsOnLayer(layer):continue
        for i in range(z.Outline().OutlineCount()):
            ch=z.Outline().COutline(i)
            shapes.append(('__KEEP_OUT__',Polygon([coords(ch.CPoint(j)) for j in range(ch.PointCount())])))
    shapes_by_layer[layer]=shapes
trees={layer:STRtree([sh for n,sh in shapes]) for layer,shapes in shapes_by_layer.items()}
added_shapes={p.F_Cu:[],p.B_Cu:[]}
processed=[]
for t in list(b.GetTracks()):
    if isinstance(t,p.PCB_VIA):continue
    net=t.GetNetname()
    if net in ['RF_ANT','RF_FEED','M_USB_DP','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19','SERVICE_USB_DP','SERVICE_USB_DM','BUCK_SW','UPS_SW','ESP_SW']:continue
    a,z=coords(t.GetStart()),coords(t.GetEnd());dx,dy=z[0]-a[0],z[1]-a[1]
    if min(abs(dx),abs(dy))<.00002 or abs(abs(dx)-abs(dy))<.00002:continue
    layer=t.GetLayer();width=p.ToMM(t.GetWidth());clearance=width/2+.205
    def obstructed(nodes):
        line=LineString(nodes)
        nearby=trees[layer].query(line.buffer(clearance))
        for index in nearby:
            n,sh=shapes_by_layer[layer][index]
            if n!=net and sh.distance(line)<=clearance:return True
        return any(n!=net and sh.distance(line)<=clearance for n,sh in added_shapes[layer])
    signx=1 if dx>0 else -1;signy=1 if dy>0 else -1;diag=min(abs(dx),abs(dy))
    options=[[a,(a[0],z[1]),z],[a,(z[0],a[1]),z],
             [a,(a[0]+signx*diag,a[1]+signy*diag),z],
             [a,(z[0]-signx*diag,z[1]-signy*diag),z]]
    chosen=None
    # Prefer axis alignment unless it is >10% longer than an available 45 path.
    clear=[nodes for nodes in options if not obstructed(nodes)]
    if clear:
        shortest=min(sum(math.dist(x,y) for x,y in zip(n,n[1:])) for n in clear)
        chosen=next((n for n in clear[:2] if sum(math.dist(x,y) for x,y in zip(n,n[1:]))<=shortest*1.1),None)
        if chosen is None:chosen=min(clear,key=lambda n:sum(math.dist(x,y) for x,y in zip(n,n[1:])))
    if chosen:
        held.append(t);b.Remove(t);r.direct(net,chosen,width,layer)
        processed.append({'net':net,'old_start':a,'old_end':z,'new_nodes':chosen,'layer':b.GetLayerName(layer),'width_mm':width})
        # A neighboring different net may have been changed; invalidate cached
        # obstacles conservatively and include new segments in future checks.
        added_shapes[layer].extend((net,LineString([aa,zz]).buffer(width/2)) for aa,zz in zip(chosen,chosen[1:]))
        if len(processed)%50==0:print('Standardized',len(processed),'segments',flush=True)

# Join collinear degree-two pieces while preserving pad/via/branch junctions.
protected=collections.defaultdict(set)
for fp in b.GetFootprints():
    for pd in fp.Pads():
        protected[pd.GetNetname()].add((pd.GetPosition().x,pd.GetPosition().y))
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):protected[t.GetNetname()].add((t.GetPosition().x,t.GetPosition().y))
merged=0
for _ in range(8):
    joints=collections.defaultdict(list)
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):continue
        for pt in [t.GetStart(),t.GetEnd()]:joints[(t.GetNetname(),t.GetLayer(),pt.x,pt.y)].append(t)
    used=set();pass_count=0
    for (net,layer,x,y),items in joints.items():
        if len(items)!=2 or (x,y) in protected[net]:continue
        a,z=items
        if id(a) in used or id(z) in used or a.GetWidth()!=z.GetWidth():continue
        def other(t):
            s,e=t.GetStart(),t.GetEnd()
            return e if s.x==x and s.y==y else s
        aa,zz=other(a),other(z);v=(aa.x-x,aa.y-y);w=(zz.x-x,zz.y-y)
        if v[0]*w[1]!=v[1]*w[0] or v[0]*w[0]+v[1]*w[1]>=0:continue
        used.update([id(a),id(z)]);held.extend([a,z]);b.Remove(a);b.Remove(z)
        r.direct(net,[coords(aa),coords(zz)],p.ToMM(a.GetWidth()),layer)
        pass_count+=1
    merged+=pass_count
    if not pass_count:break

b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE),b)
after=angular_stats(b)
report={'date':'2026-11-24','base_PCB_sha256':sha,'candidate_PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),
        'original_unchanged':hashlib.sha256(base.read_bytes()).hexdigest()==sha,'angle_before':before,'angle_after':after,
        'power_changes':changes,'standardized_segment_count':len(processed),'collinear_pieces_merged':merged,'segment_changes':processed,
        'manufacturing_ready':False,'remaining_scope':'Full placement, USB/RF, power transient/thermal and exact BOM qualification remain.'}
assert report['original_unchanged']
(OUT.parent/'candidate-changes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for t in held:t.thisown=False
print(json.dumps({k:v for k,v in report.items() if k!='segment_changes'},ensure_ascii=False,indent=2))
