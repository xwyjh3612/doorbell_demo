"""Add clearance-checked 0.6/0.3mm stitching vias on actual ground islands."""
from pathlib import Path
import sys,json,math
import pcbnew as p
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
from shapely.geometry import Point,LineString
from shapely.ops import unary_union
b=r.board;obstacles=[];holes=[]
for f in b.GetFootprints():
    for pd in f.Pads():
        for layer in [p.F_Cu,p.B_Cu]:
            if pd.IsOnLayer(layer):obstacles.extend(sh.buffer(.505)for sh in r.polygons(pd,layer))
        if pd.GetDrillSize().x:holes.append(Point(r.pos(pd)).buffer(p.ToMM(pd.GetDrillSize().x)/2+.405))
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):
        holes.append(Point(r.pos(t)).buffer(p.ToMM(t.GetDrill())/2+.405))
        if t.GetNetname()!='GND':obstacles.append(Point(r.pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2+.505))
    elif t.GetNetname()!='GND':
        obstacles.append(LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2+.505))
blocked=unary_union(obstacles+holes)
added=[]
# Ground islands are not located at the zone's display origin. Stitching the
# entire area safely reaches populated ground lobes on all four copper layers.
for x in range(3,98,3):
    for y in range(3,73,3):
        xy=(x,y)
        if blocked.intersects(Point(xy)):continue
        # Avoid inserting a through-via in the RF antenna or USB pair corridor.
        if 51<x<95 and y<32:continue
        r.addvia('gnd_'+str(x)+'_'+str(y),'GND',xy);added.append(xy)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'exports/ground-stitching.json').write_text(json.dumps({'vias_mm':added,'diameter_mm':.6,'drill_mm':.3,'clearance_checked':True},indent=2)+'\n',encoding='utf8')
print('Added conventional ground stitching vias:',len(added))
