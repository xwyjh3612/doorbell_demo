from pathlib import Path
import sys,json,math,pcbnew as p
from two_layer_support import load
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import Polygon,Point
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
b=p.LoadBoard(str(FILE));held=[]
for t in list(b.GetTracks()):
    if t.GetNetname()=='SUPPLY_BAT_N47':held.append(t);b.Remove(t)
p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
r,m=load();b=r.board;report=[]
for ref,n in [('U18',6),('U18',8),('U7',24)]:
    try:r.escapevia(ref+'_end_'+str(n),(ref,n),diameter=.6,drill=.3,neck=.2)
    except (RuntimeError,AssertionError) as e:print('escape',ref,n,e,flush=True)
def via_for(ref,n,name):
    pd=r.pad(ref,n);vs=sorted([t for t in b.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()==pd.GetNetname()],key=lambda t:math.dist(r.pos(pd),r.pos(t)))
    if vs and math.dist(r.pos(pd),r.pos(vs[0]))<4:r.virtual[name]=vs[0];return name,0
    return ref,n
for a,z in [(via_for('U18',6,'backup_via'),('C73',1)),(via_for('U18',8,'st_via'),via_for('U7',24,'st_esp')),
    (via_for('U18',8,'st_via'),('R72',2)),(('R68',1),('C67',1)),(('R70',1),('C71',1))]:
    try:m.route(r,a,z,width=.2,step=.1,bounds=(.6,.6,99.4,74.4));report.append({'from':a,'to':z,'routed':True})
    except (RuntimeError,AssertionError) as e:report.append({'from':a,'to':z,'routed':False,'reason':str(e)})
    p.SaveBoard(str(FILE),b)
# Join remaining physical ground islands to a through-hole ground anchor.
for zone in list(b.Zones()):
    if zone.GetIsRuleArea() or zone.GetNetname()!='GND':continue
    ps=zone.GetFilledPolysList(zone.GetLayer())
    for i in range(ps.OutlineCount()):
        ch=ps.COutline(i);poly=Polygon([(p.ToMM(ch.CPoint(j).x),p.ToMM(ch.CPoint(j).y)) for j in range(ch.PointCount())]).buffer(0)
        if poly.area<.05:continue
        pt=poly.representative_point();name='remaining_ground_'+str(len(report));r.virtual[name]=r.Endpoint('GND',(pt.x,pt.y))
        r.virtual[name].IsOnLayer=lambda layer,la=zone.GetLayer():layer==la
        try:
            r.escapevia('via_'+name,(name,0),diameter=.6,drill=.3,neck=.2,layer=zone.GetLayer())
            m.route(r,('via_'+name,0),('TP6',1),width=.2,step=.15,bounds=(.6,.6,99.4,74.4))
            report.append({'net':'GND','connected':True})
        except (RuntimeError,AssertionError) as e:report.append({'net':'GND','connected':False,'reason':str(e)})
        p.SaveBoard(str(FILE),b)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'exports/remaining-connections.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(report)
