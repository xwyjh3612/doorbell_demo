"""Connect filled copper islands by real vias/copper, never waive the DRC."""
from pathlib import Path
import json,math,sys,pcbnew as p
from two_layer_support import load
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
r,m=load();b=r.board
def areas(z):
    ps=z.GetFilledPolysList(z.GetLayer());out=[]
    for i in range(ps.OutlineCount()):
        ch=ps.COutline(i);q=Polygon([(p.ToMM(ch.CPoint(j).x),p.ToMM(ch.CPoint(j).y)) for j in range(ch.PointCount())]).buffer(0)
        out.extend(list(q.geoms) if hasattr(q,'geoms') else [q])
    return [q for q in out if q.area>.005]
grounds={l:unary_union([a for z in b.Zones() if z.GetNetname()=='GND' and z.GetLayer()==l and not z.GetIsRuleArea() for a in areas(z)]) for l in [p.F_Cu,p.B_Cu]}
obs=[]
for f in b.GetFootprints():
    for pd in f.Pads():
        for l in [p.F_Cu,p.B_Cu]:
            if pd.IsOnLayer(l):obs.extend(sh.buffer(.505) for sh in r.polygons(pd,l))
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):obs.append(Point(r.pos(t)).buffer(.56))
    elif t.GetNetname()!='GND':obs.append(LineString([r.pos(t),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2+.505))
blocked=unary_union(obs);count=0
for l in [p.F_Cu,p.B_Cu]:
    for z in [z for z in b.Zones() if z.GetNetname()=='GND' and z.GetLayer()==l and not z.GetIsRuleArea()]:
        for a in areas(z):
            overlap=a.intersection(grounds[p.B_Cu if l==p.F_Cu else p.F_Cu]).buffer(-.31).difference(blocked)
            if overlap.is_empty:continue
            pt=overlap.representative_point();xy=(pt.x,pt.y)
            r.addvia('ground_stitch_'+str(count),'GND',xy);count+=1
            blocked=blocked.union(Point(xy).buffer(.56))
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
report={'ground_stitch_vias_added':count,'power_connections':[]};print('Ground stitch vias',count,flush=True)
hub={'VIN_PROTECTED':('Q6',2),'BAT_SENSE_IN':('J23',1),'BAT_BOOST_5V':('U15',7),'SYS_5V':('U18',2),'CELL_NEG':('J23',2)}
for z in list(b.Zones()):
    net=z.GetNetname()
    if z.GetIsRuleArea() or net not in hub:continue
    for k,a in enumerate(areas(z)):
        if a.contains(Point(r.pos(r.pad(*hub[net])))):continue
        pt=a.representative_point();name='plane_'+str(len(report['power_connections']));r.virtual[name]=r.Endpoint(net,(pt.x,pt.y))
        r.virtual[name].IsOnLayer=lambda layer,la=z.GetLayer():layer==la
        aa=(name,0);zz=hub[net]
        try:m.route(r,aa,zz,width=.4,step=.1,bounds=(.6,.6,99.4,74.4));item={'net':net,'connected':True}
        except (RuntimeError,AssertionError) as e:item={'net':net,'connected':False,'reason':str(e)}
        report['power_connections'].append(item);p.SaveBoard(str(FILE),b)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'exports/plane-connections.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(report)
