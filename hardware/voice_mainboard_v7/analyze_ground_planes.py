"""Read-only geometric component audit of filled GND, including polygon holes."""
import collections,json,sys
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'build/cad-tools/route-python'))
from shapely.geometry import Point,LineString,Polygon
from shapely.strtree import STRtree
FILE=ROOT.parents[1]/'build/v7-back-routes-20261124/voice_mainboard_v7.kicad_pcb'
if len(sys.argv)>1:FILE=Path(sys.argv[1]).resolve()
b=p.LoadBoard(str(FILE))
def xy(v):return p.ToMM(v.x),p.ToMM(v.y)
def ring(c):return [xy(c.CPoint(j))for j in range(c.PointCount())]
shapes=[];items=[]
def add(layer,shape,info):
    if not shape.is_valid:shape=shape.buffer(0)
    shapes.append(shape);items.append(dict(layer=layer,**info))
for z in b.Zones():
    if z.GetNetname()!='GND':continue
    for layer in [p.F_Cu,p.B_Cu]:
        if not z.IsOnLayer(layer):continue
        ps=z.GetFilledPolysList(layer)
        for i in range(ps.OutlineCount()):
            add(layer,Polygon(ring(ps.COutline(i)),[ring(ps.CHole(j,i))for j in range(ps.HoleCount(i))]),{'kind':'zone','outline':i,'uuid':z.m_Uuid.AsString()})
for fp in b.GetFootprints():
    for pd in fp.Pads():
        if pd.GetNetname()!='GND':continue
        for layer in [p.F_Cu,p.B_Cu]:
            if not pd.IsOnLayer(layer):continue
            ps=pd.GetEffectivePolygon(layer)
            for i in range(ps.OutlineCount()):add(layer,Polygon(ring(ps.COutline(i))),{'kind':'pad','ref':fp.GetReference(),'pad':pd.GetNumber(),'uuid':pd.m_Uuid.AsString()})
for t in b.GetTracks():
    if t.GetNetname()!='GND':continue
    if isinstance(t,p.PCB_VIA):
        for layer in [p.F_Cu,p.B_Cu]:add(layer,Point(xy(t.GetPosition())).buffer(p.ToMM(t.GetWidth(layer))/2),{'kind':'via','uuid':t.m_Uuid.AsString()})
    else:add(t.GetLayer(),LineString([xy(t.GetStart()),xy(t.GetEnd())]).buffer(p.ToMM(t.GetWidth())/2),{'kind':'track','uuid':t.m_Uuid.AsString()})
parents=list(range(len(shapes)))
def find(i):
    while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
    return i
def join(i,j):parents[find(i)]=find(j)
tree=STRtree(shapes);vertical=collections.defaultdict(list)
for i,sh in enumerate(shapes):
    for j in tree.query(sh.buffer(.000002)):
        if items[i]['layer']==items[j]['layer']and sh.distance(shapes[j])<.000003:join(i,int(j))
    if items[i]['kind']in ['pad','via']:vertical[items[i]['uuid']].append(i)
for ids in vertical.values():
    for i in ids[1:]:join(i,ids[0])
groups=collections.defaultdict(list)
for i in range(len(shapes)):groups[find(i)].append(i)
report=[]
for ids in sorted(groups.values(),key=len,reverse=True):
    report.append({'size':len(ids),'pads':[items[i]for i in ids if items[i]['kind']=='pad'],'vias':[dict(items[i],position_mm=[shapes[i].centroid.x,shapes[i].centroid.y])for i in ids if items[i]['kind']=='via'],'zones':[dict(items[i],bounds=shapes[i].bounds,area=shapes[i].area)for i in ids if items[i]['kind']=='zone'],'tracks':[dict(items[i],bounds=shapes[i].bounds)for i in ids if items[i]['kind']=='track']})
OUT=FILE.parent/'ground-components.json';OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'components':len(report),'small_components':report[1:]},ensure_ascii=False,indent=2))
