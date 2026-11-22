"""Connect populated ground islands using ordinary off-pad 0.6/0.3 mm vias.

Both the surface search and via search include module antenna rule areas.
Native DRC is still required after filling; failures are reported, not hidden.
"""
from pathlib import Path
import sys, types, json, math
import pcbnew as p

ROOT = Path(__file__).resolve().parent
file = ROOT / 'voice_mainboard_v4.kicad_pcb'
sys.argv = [__file__, str(file)]
source = (ROOT.parent / 'voice_mainboard_v3/route_helpers.py').read_text(encoding='utf8')
source = source.replace('    blocked=unary_union(all_obstacles);fblocked=unary_union(front)', '''    for z in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not z.GetIsRuleArea():continue
        for i in range(z.Outline().OutlineCount()):
            ring=z.Outline().COutline(i)
            sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
            all_obstacles.append(sh.buffer(diameter/2+.005))
            if z.IsOnLayer(layer):front.append(sh.buffer(neck/2+.005))
    blocked=unary_union(all_obstacles);fblocked=unary_union(front)''')
source = source.replace('    obstacle=unary_union(obstacles)', '''    for z in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not z.GetIsRuleArea()or not z.IsOnLayer(layer):continue
        for i in range(z.Outline().OutlineCount()):
            ring=z.Outline().COutline(i)
            obstacles.append(Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]).buffer(width/2+.005))
    obstacle=unary_union(obstacles)''')
r = types.ModuleType('ground_search')
exec(compile(source, 'ground_search', 'exec'), r.__dict__)
pairs = [('U12',3),('R5',2),('U1',95),('U5',2),('R60',2),('C18',2),('C28',2),('U14',3),('C10',2)]
report=[]
for index,pair in enumerate(pairs):
    pd=r.pad(*pair);xy=r.pos(pd);layer=p.F_Cu if pd.IsOnLayer(p.F_Cu)else p.B_Cu
    vias=sorted([t for t in r.board.GetTracks()if isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND'],key=lambda t:math.dist(xy,r.pos(t)))
    ok=False
    for t in vias:
        if math.dist(xy,r.pos(t))>5:break
        pt=r.pos(t);name='ground_target_'+str(index);r.virtual[name]=r.Endpoint('GND',pt)
        bounds=(min(xy[0],pt[0])-1.5,min(xy[1],pt[1])-1.5,max(xy[0],pt[0])+1.5,max(xy[1],pt[1])+1.5)
        try:r.route(pair,(name,0),layer=layer,width=.2,step=.05,bounds=bounds)
        except RuntimeError:continue
        report.append({'pad':pair,'via_mm':pt,'connected':True,'method':'existing_via'});ok=True;break
    if not ok:
        try:
            name='ground_escape_'+str(index)
            r.escapevia(name,pair,diameter=.6,drill=.3,neck=.2)
            report.append({'pad':pair,'via_mm':r.pos(r.virtual[name]),'connected':True,'method':'off_pad_via'})
        except RuntimeError as error:
            report.append({'pad':pair,'connected':False,'reason':str(error)})
    p.SaveBoard(str(file),r.board)
r.board.BuildConnectivity();assert p.ZONE_FILLER(r.board).Fill(r.board.Zones())
p.SaveBoard(str(file),r.board)
(ROOT/'exports/ground-lobe-connections.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Connected ground lobes:',sum(item['connected']for item in report),'/',len(report))
