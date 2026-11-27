"""Start a distinct V7 working board with local decoupling improvements.

V6 remains intact. Outputs are engineering work, never production release.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import types
import math
import pcbnew as p

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
BASE=REPO/'build/v6-layout-refinement-20261124/candidate'
OUT=ROOT.parent/'voice_mainboard_v7'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'exports').mkdir(exist_ok=True)
FILE=OUT/'voice_mainboard_v7.kicad_pcb'
for suffix in ['.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru']:
    shutil.copy2(BASE/('voice_mainboard_v6'+suffix),OUT/('voice_mainboard_v7'+suffix))
for name in ['VoiceV2.kicad_sym','fp-lib-table','sym-lib-table']:
    shutil.copy2(BASE/name,OUT/name)
shutil.copytree(BASE/'VoiceV2.pretty',OUT/'VoiceV2.pretty',dirs_exist_ok=True)
design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
parts={q['ref']:q for q in design['parts']}
source=(ROOT.parent/'voice_mainboard_v3/route_helpers.py').read_text(encoding='utf-8')
# Prevent path shortening from making arbitrary-angle segments in the new loops.
old='''        j=len(points)-1
        while j>i+1 and obstacle.intersects(LineString([points[i],points[j]])):j-=1'''
new='''        j=len(points)-1
        def aligned(a,z):
            dx,dy=abs(a[0]-z[0]),abs(a[1]-z[1])
            return min(dx,dy)<1e-5 or abs(dx-dy)<1e-5
        while j>i+1 and (not aligned(points[i],points[j]) or obstacle.intersects(LineString([points[i],points[j]]))):j-=1'''
assert old in source
source=source.replace(old,new)
source=source.replace('    obstacle=unary_union(obstacles)', '''    for z in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not z.GetIsRuleArea()or not z.IsOnLayer(layer):continue
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
r=types.ModuleType('v7_local_router');exec(compile(source,'v7_local_router','exec'),r.__dict__)
b=r.board
fps={fp.GetReference():fp for fp in b.GetFootprints()}
held=[]
changes=[]

def save():
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)

placements=[('C62',91.6,22.4,180,('U14',7)),('C61',90.1,24.0,180,('U14',8)),
            ('C67',37.3,58.2,180,('U16',4)),('C68',45.475,59.5,0,('U16',5))]
for ref,x,y,angle,target in placements:
    f=fps[ref]
    oldxy=r.pos(f)
    shapes={pd.GetNetname():r.polygons(pd,p.F_Cu) for pd in f.Pads()}
    # Remove only copper that attaches at an old pad; shared-net branches stay.
    from shapely.geometry import Point,LineString
    attached=[]
    for t in list(b.GetTracks()):
        if isinstance(t,p.PCB_VIA):continue
        if t.GetLayer()!=p.F_Cu or t.GetNetname() not in shapes:continue
        ends=[(p.ToMM(z.x),p.ToMM(z.y))for z in [t.GetStart(),t.GetEnd()]]
        if any(sh.buffer(.01).intersects(Point(z))for z in ends for sh in shapes[t.GetNetname()]):
            attached.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});held.append(t);b.Remove(t)
    from shapely.geometry import box
    def court(fp):
        points=[]
        for item in fp.GraphicalItems():
            if item.GetLayer()==p.F_CrtYd:
                points.extend([r.pos(r.Endpoint('',(p.ToMM(item.GetStart().x),p.ToMM(item.GetStart().y)))),r.pos(r.Endpoint('',(p.ToMM(item.GetEnd().x),p.ToMM(item.GetEnd().y))))])
        if not points:return None
        return box(min(a for a,z in points),min(z for a,z in points),max(a for a,z in points),max(z for a,z in points))
    other_courts=[v for fp in b.GetFootprints() if fp.GetReference()!=ref for v in [court(fp)] if v is not None]
    obstacles=[]
    for fp in b.GetFootprints():
        if fp.GetReference()==ref:continue
        for pd in fp.Pads():
            if pd.IsOnLayer(p.F_Cu):obstacles.extend((pd.GetNetname(),sh) for sh in r.polygons(pd,p.F_Cu))
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            obstacles.append((t.GetNetname(),Point(r.pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2)))
        elif t.GetLayer()==p.F_Cu:
            obstacles.append((t.GetNetname(),LineString([(p.ToMM(z.x),p.ToMM(z.y))for z in [t.GetStart(),t.GetEnd()]]).buffer(p.ToMM(t.GetWidth())/2)))
    chosen=None
    choices=[(x+dx*.25,y+dy*.25,aa)for dx in range(-8,9)for dy in range(-8,9)for aa in [angle,(angle+90)%360]]
    for cx,cy,aa in sorted(choices,key=lambda z:math.hypot(z[0]-x,z[1]-y)):
        f.SetPosition(p.VECTOR2I(p.FromMM(cx),p.FromMM(cy)));f.SetOrientationDegrees(aa)
        fc=court(f)
        if any(fc.intersection(z).area>1e-9 for z in other_courts):continue
        clear=True
        for pd in f.Pads():
            for sh in r.polygons(pd,p.F_Cu):
                if any(net!=pd.GetNetname() and sh.distance(obstacle)<.205 for net,obstacle in obstacles):clear=False;break
            if not clear:break
        if clear:chosen=(cx,cy,aa);break
    if chosen is None:raise RuntimeError('No collision-free local placement for '+ref)
    x,y,angle=chosen
    parts[ref].update(x=x,y=y,angle=angle)
    a,z=r.pos(r.pad(ref,1)),r.pos(r.pad(*target))
    bounds=(min(a[0],z[0])-4,min(a[1],z[1])-4,max(a[0],z[0])+4,max(a[1],z[1])+4)
    result={'ref':ref,'old_xy':oldxy,'new_xy':[x,y],'angle':angle,'target':target,'removed_attached_segments':attached}
    try:
        r.route((ref,1),target,width=.25,step=.025,bounds=bounds)
        result['power_routed']=True
    except (RuntimeError,AssertionError) as e:
        result.update(power_routed=False,error=str(e))
    try:
        r.escapevia('v7_gnd_'+ref,(ref,2),diameter=.6,drill=.3,neck=.3)
        result['ground_connected_by_via']=True
    except (RuntimeError,AssertionError) as e:
        result.update(ground_connected_by_via=False,ground_error=str(e))
    changes.append(result);save();print(json.dumps(result,ensure_ascii=False),flush=True)

# Preserve the supply connection formerly passing through the moved capacitors.
for ref,n in [('U14',8),('U16',5)]:
    try:
        r.escapevia('v7_supply_'+ref,(ref,n),diameter=.6,drill=.3,neck=.25)
        changes.append({'supply_pad':[ref,n],'supply_via':True})
    except (RuntimeError,AssertionError) as e:
        changes.append({'supply_pad':[ref,n],'supply_via':False,'error':str(e)})
save()

design.update(revision='V7-ENGINEERING-WORK-20261124',status='LOCAL POWER LAYOUT WORK; NOT RELEASED',parts=list(parts.values()),manufacturing_ready=False)
design['parent_PCB_sha256']=hashlib.sha256((BASE/'voice_mainboard_v6.kicad_pcb').read_bytes()).hexdigest()
(OUT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'exports/power-layout-changes.json').write_text(json.dumps({'date':'2026-11-24','changes':changes,'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'manufacturing_ready':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for t in held:t.thisown=False
print('Saved distinct V7 local power layout work')
