from pathlib import Path
import sys,json
import pcbnew as p
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import Polygon,Point
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
out=[]
for z in b.Zones():
    if z.GetNetname()!='GND':continue
    q=z.GetFilledPolysList(z.GetLayer())
    for i in range(q.OutlineCount()):
        ch=q.COutline(i);pts=[(p.ToMM(ch.CPoint(j).x),p.ToMM(ch.CPoint(j).y))for j in range(ch.PointCount())]
        if len(pts)<3:continue
        poly=Polygon(pts).buffer(0)
        if poly.area>150:continue
        pads=[]
        for fp in b.GetFootprints():
            for pd in fp.Pads():
                if pd.IsOnLayer(z.GetLayer())and pd.GetNetname()=='GND'and poly.buffer(.2).intersects(Point(p.ToMM(pd.GetPosition().x),p.ToMM(pd.GetPosition().y))):pads.append([fp.GetReference(),pd.GetNumber()])
        via_count=sum(poly.buffer(.1).intersects(Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y)))for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND')
        if not via_count and pads:
            xy=poly.representative_point();out.append({'layer':b.GetLayerName(z.GetLayer()),'area_mm2':poly.area,'point':[xy.x,xy.y],'pads':pads,'via_count':via_count})
print(json.dumps(out,indent=2))
(root/'exports/ground-island-inspection.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
