"""Read-only placement feasibility for a real zero-ohm crossover resistor.

Check complete standard lands and courtyards against existing copper. A result
would require an explicit schematic/BOM change and new native checks before use.
"""
import json
import os
from pathlib import Path
from comparison_route_geometry import b,FILE,p,pos,polys,layers,outline,rules,required_clearance
from shapely.geometry import Point,LineString,Polygon
from shapely.strtree import STRtree
import numpy as np

net=os.environ['A18_BRIDGE_NET']
fields=[np.load(os.environ['A18_BRIDGE_MAP_A']),np.load(os.environ['A18_BRIDGE_MAP_B'])]
def reachable(field,xy,li):
    ix=round((xy[0]-field['xs'][0])/(field['xs'][1]-field['xs'][0]))
    iy=round((xy[1]-field['ys'][0])/(field['ys'][1]-field['ys'][0]))
    return 0<=ix<len(field['xs'])and 0<=iy<len(field['ys'])and field['reachable'][li,iy,ix]
def courtyard(f):
    f.BuildCourtyardCaches();sh=f.GetCourtyard(f.GetLayer())
    return [Polygon([(p.ToMM(q.CPoint(i).x),p.ToMM(q.CPoint(i).y))for i in range(q.PointCount())])
        for q in[sh.COutline(k)for k in range(sh.OutlineCount())]if q.PointCount()>=3]
root=Path(__file__).resolve().parents[2]
records=[]
for side in layers:
    li=layers.index(side)
    shapes=[];names=[]
    for f in b.GetFootprints():
        for d in f.Pads():
            if d.IsOnLayer(side):
                for sh in polys(d,side):shapes.append(sh);names.append(d.GetNetname())
    for t in b.GetTracks():
        if not t.IsOnLayer(side):continue
        sh=Point(pos(t)).buffer(p.ToMM(t.GetWidth(side))/2)if isinstance(t,p.PCB_VIA)else LineString([(p.ToMM(q.x),p.ToMM(q.y))for q in[t.GetStart(),t.GetEnd()]]).buffer(p.ToMM(t.GetWidth())/2)
        shapes.append(sh);names.append(t.GetNetname())
    tree=STRtree(shapes)
    courts=[sh for f in b.GetFootprints()if f.GetLayer()==side for sh in courtyard(f)]
    court_tree=STRtree(courts)
    for name in ['R_0805_2012Metric','R_1206_3216Metric']:
        fp=p.FootprintLoad(str(root/'build/cad-tools/kicad/share/kicad/footprints/Resistor_SMD.pretty'),name)
        if side==p.B_Cu:fp.Flip(fp.GetPosition(),False)
        for d in fp.Pads():d.SetNet(b.FindNet(net))
        pads=sorted(fp.Pads(),key=lambda q:q.GetNumber())
        for angle in [0,90,180,270]:
            fp.SetOrientationDegrees(angle)
            for x in np.arange(7,72,.25):
                for y in np.arange(1,72,.25):
                    fp.SetPosition(p.VECTOR2I(p.FromMM(float(x)),p.FromMM(float(y))))
                    points=[pos(d)for d in pads]
                    if not reachable(fields[0],points[0],li)or not reachable(fields[1],points[1],li):continue
                    ok=True
                    for d in pads:
                        for sh in polys(d,side):
                            if not outline.buffer(-.501).covers(sh):ok=False;break
                            for i in tree.query(sh.buffer(.202)):
                                if names[int(i)]!=net and sh.distance(shapes[int(i)])<required_clearance(net,names[int(i)]):ok=False;break
                            if any(z.IsOnLayer(side)and z.GetDoNotAllowPads()and area.intersects(sh)for z,area in rules):ok=False
                        if not ok:break
                    if not ok:continue
                    for sh in courtyard(fp):
                        if any(sh.intersection(courts[int(i)]).area>1e-8 for i in court_tree.query(sh)):
                            ok=False;break
                        if any(z.IsOnLayer(side)and z.GetDoNotAllowFootprints()and area.intersects(sh)for z,area in rules):ok=False
                    if ok:records.append({'footprint':name,'side':'F'if side==p.F_Cu else'B','x':float(x),'y':float(y),'angle':angle,'pads':points})
        fp.thisown=False
    print('Candidates',p.LayerName(side),len(records),flush=True)
(FILE.parent/'exports'/('bridge-candidates-'+net+'.json')).write_text(json.dumps(records,indent=2),encoding='utf-8')
print(json.dumps(records[:10],indent=2),flush=True)
