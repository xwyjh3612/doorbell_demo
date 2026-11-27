"""Plan narrow-pad escape on every copper layer; retain native DRC authority.

This tool never removes nets or changes pad numbering. Local optional rip-up is
reported explicitly, and all disturbed nets must be reconnected afterwards.
"""
from pathlib import Path
import json, math, os, sys, shutil
import pcbnew as p
from comparison_route_geometry import b, FILE, pos, polys, layers, rules, outline, required_clearance
from shapely.geometry import Point, LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=FILE.parent
(ROOT/'exports').mkdir(exist_ok=True)
fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,n):
    number,index=(str(n).split('@',1)+['0'])[:2] if '@'in str(n)else(str(n),'0')
    return [d for d in fps[ref].Pads()if d.GetNumber()==number][int(index)]
static_masks={};dynamic_index=None
def obstruction(net,point,start,layer,diameter=.45,neck=.16,via_drill=.2):
    global dynamic_index
    v=Point(point);line=LineString([start,point]);blocked=[]
    if not outline.buffer(-diameter/2-.501).covers(v):return ['board-edge']
    key=(net,layer,diameter,neck,via_drill)
    if key not in static_masks:
        via_masks=[];neck_masks=[]
        for f in b.GetFootprints():
            for d in f.Pads():
                for l in layers:
                    if not d.IsOnLayer(l):continue
                    for sh in polys(d,l):
                        via_masks.append(sh.buffer(diameter/2+.05 if d.GetNetname()==net else diameter/2+required_clearance(net,d.GetNetname()),quad_segs=24))
                        if l==layer and d.GetNetname()!=net:neck_masks.append(sh.buffer(neck/2+required_clearance(net,d.GetNetname()),quad_segs=24))
                if d.GetDrillSize().x:via_masks.append(Point(pos(d)).buffer(p.ToMM(d.GetDrillSize().x)/2+via_drill/2+.251))
        for z,sh in rules:
            if z.GetDoNotAllowVias():via_masks.append(sh.buffer(diameter/2+.011))
            if z.IsOnLayer(layer)and z.GetDoNotAllowTracks():neck_masks.append(sh.buffer(neck/2+.011))
        static_masks[key]=(unary_union(via_masks),unary_union(neck_masks))
    via_mask,neck_mask=static_masks[key]
    if via_mask.intersects(v)or neck_mask.intersects(line):return ['pad/hole/rule-area']
    if dynamic_index is None:
        tracks=list(b.GetTracks());shapes=[]
        for t in tracks:
            sh=Point(pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2)if isinstance(t,p.PCB_VIA)else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2)
            shapes.append(sh)
        dynamic_index=(tracks,STRtree(shapes))
    tracks,tree=dynamic_index
    # Broad spatial queries are followed by the same exact distance checks;
    # cached geometry never replaces native DRC or alters physical pads.
    nearby=set(int(i)for i in tree.query(v.buffer(max(.55,diameter/2+.205))))
    nearby.update(int(i)for i in tree.query(line.buffer(neck/2+.205)))
    for i in nearby:
        t=tracks[i]
        if isinstance(t,p.PCB_VIA):
            if Point(pos(t)).distance(v)<p.ToMM(t.GetDrill())/2+via_drill/2+.251:blocked.append(str(t.m_Uuid.AsString()))
            if t.GetNetname()!=net and (Point(pos(t)).distance(v)<p.ToMM(t.GetWidth(p.F_Cu))/2+diameter/2+required_clearance(net,t.GetNetname()) or Point(pos(t)).distance(line)<p.ToMM(t.GetWidth(p.F_Cu))/2+neck/2+required_clearance(net,t.GetNetname())):blocked.append(str(t.m_Uuid.AsString()))
        elif t.GetNetname()!=net:
            a,z=t.GetStart(),t.GetEnd();sh=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))])
            if sh.distance(v)<p.ToMM(t.GetWidth())/2+diameter/2+required_clearance(net,t.GetNetname()) or(t.GetLayer()==layer and sh.distance(line)<p.ToMM(t.GetWidth())/2+neck/2+required_clearance(net,t.GetNetname())):blocked.append(str(t.m_Uuid.AsString()))
    return sorted(set(blocked))

if __name__=='__main__':
    targets=[q.split('.') for q in os.environ['A18_ESCAPE_PADS'].split(',')]
    objects={str(t.m_Uuid.AsString()):t for t in b.GetTracks()};report=[];held=[]
    if os.environ.get('A18_ESCAPE_REPLACE')=='1':
        prior=ROOT/'exports/local-escape-review.json'
        if prior.exists():
            for entry in json.loads(prior.read_text(encoding='utf-8')):
                if entry.get('pad') not in targets or not entry.get('success'):
                    continue
                target=entry['via_mm'];d=pad(*entry['pad'])
                for t in list(b.GetTracks()):
                    at_via=isinstance(t,p.PCB_VIA) and math.dist(pos(t),target)<.001
                    at_neck=not isinstance(t,p.PCB_VIA) and math.dist((p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),pos(d))<.001 and math.dist((p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y)),target)<.001
                    if t.GetNetname()==d.GetNetname() and (at_via or at_neck):
                        held.append(t);b.Remove(t);objects.pop(t.m_Uuid.AsString(),None)
    for ref,n in targets:
        dynamic_index=None
        d=pad(ref,n);net=d.GetNetname();start=pos(d);layer=fps[ref].GetLayer();candidates=[]
        power=net in ['SYS_5V','VIN_PROTECTED','MODEM_3V8','BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','BUCK_SW','UPS_SW','ESP_SW'] and os.environ.get('A18_POWER_ESCAPE')=='1'
        diameter=float(os.environ.get('A18_POWER_VIA_MM','.6')) if power else .45
        drill=float(os.environ.get('A18_POWER_DRILL_MM','.3')) if power else .2;neck=.25 if power else .16
        assert diameter>=drill+.2,'Keep at least 0.1mm annular ring'
        centre=pos(fps[ref]);outward=math.degrees(math.atan2(start[1]-centre[1],start[0]-centre[0]))%360
        angles=sorted(range(0,360,45),key=lambda a:abs((a-outward+180)%360-180))
        radii=[.8,1,1.2,1.4,1.6,1.8,2,2.2,2.4,2.8,3.2,3.6,4]if power else[.8,1,1.2,1.4,1.6,1.8,2,2.2,2.4]
        if not power and os.environ.get('A18_SIGNAL_ESCAPE_MAX_MM'):
            radii += [r for r in [2.8,3.2,3.6,4]if r<=float(os.environ['A18_SIGNAL_ESCAPE_MAX_MM'])]
        explicit=json.loads(os.environ.get('A18_EXPLICIT_ESCAPE_POINTS','{}')).get(ref+'.'+n)
        options=[(math.dist(start,explicit),tuple(explicit))] if explicit else [(radius,(start[0]+radius*math.cos(math.radians(angle)),start[1]+radius*math.sin(math.radians(angle)))) for radius in radii for angle in angles]
        for radius,pt in options:
                blocks=obstruction(net,pt,start,layer,diameter,neck,drill)
                if any(q not in objects or objects[q].IsLocked() for q in blocks):continue
                candidates.append((len(blocks),radius,pt,blocks))
                if not blocks:break
        if not candidates:report.append({'pad':[ref,n],'success':False});continue
        candidates.sort(key=lambda q:(q[0],q[1]))
        _,radius,pt,blocks=candidates[0]
        if blocks and os.environ.get('A18_ESCAPE_RIPUP')!='1':
            report.append({'pad':[ref,n],'success':False,'best_candidate':pt,'blocking_tracks':[{'uuid':q,'net':objects[q].GetNetname(),'layer':p.LayerName(objects[q].GetLayer())}for q in blocks]});continue
        removed=[]
        for q in blocks:
            t=objects[q];removed.append({'uuid':q,'net':t.GetNetname(),'layer':p.LayerName(t.GetLayer())});held.append(t);b.Remove(t);del objects[q]
        track=p.PCB_TRACK(b);track.SetStart(d.GetPosition());track.SetEnd(p.VECTOR2I(p.FromMM(pt[0]),p.FromMM(pt[1])));track.SetWidth(p.FromMM(neck));track.SetLayer(layer);track.SetNetCode(d.GetNetCode());b.Add(track)
        via=p.PCB_VIA(b);via.SetPosition(track.GetEnd());via.SetWidth(p.FromMM(diameter));via.SetDrill(p.FromMM(drill));via.SetViaType(p.VIATYPE_THROUGH);via.SetLayerPair(p.F_Cu,p.B_Cu);via.SetNetCode(d.GetNetCode());b.Add(via)
        objects[str(track.m_Uuid.AsString())]=track;objects[str(via.m_Uuid.AsString())]=via
        report.append({'pad':[ref,n],'success':True,'via_mm':pt,'neck_mm':radius,'neck_width_mm':neck,'via_diameter_mm':diameter,'removed_tracks':removed})
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    (ROOT/'exports/local-escape-review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'targets':len(report),'escaped':sum(q.get('success',False)for q in report),
                      'not_escaped':[q['pad']for q in report if not q.get('success')],
                      'removed_tracks':sum(len(q.get('removed_tracks',[]))for q in report)},indent=2))
    for t in held:t.thisown=False
