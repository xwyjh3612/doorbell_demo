"""Join remaining populated ground lobes to real existing ground vias.

Uses bent surface traces, so a crowded opposite layer does not force a new
through-hole into an unavailable position.
"""
from pathlib import Path
import sys,json,math
import pcbnew as p
root=Path(__file__).resolve().parent
requested=sys.argv[1:]
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
b=r.board;report=[]
try:
    pairs=[(text.split(':')[0],int(text.split(':')[1]))for text in requested]if requested else[('C40',2),('C39',2),('C53',2),('C50',2)]
    for index,pair in enumerate(pairs):
        pd=r.pad(*pair);xy=r.pos(pd);layer=p.F_Cu if pd.IsOnLayer(p.F_Cu)else p.B_Cu
        vias=sorted([t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND'],key=lambda t:math.dist(xy,r.pos(t)))
        ok=False
        for t in vias:
            if math.dist(xy,r.pos(t))>8:break
            name='existing_ground_'+str(index);pt=r.pos(t);r.virtual[name]=r.Endpoint('GND',pt)
            bounds=(min(xy[0],pt[0])-3,min(xy[1],pt[1])-3,max(xy[0],pt[0])+3,max(xy[1],pt[1])+3)
            try:r.route(pair,(name,0),layer=layer,width=.2,step=.025,bounds=bounds)
            except RuntimeError:continue
            report.append({'pad':pair,'via':pt,'layer':b.GetLayerName(layer)});ok=True;break
        if not ok:
            name='fine_ground_'+str(index)
            r.escapevia(name,pair,diameter=.45,drill=.2,neck=.2)
            report.append({'pad':pair,'via':r.pos(r.virtual[name]),'layer':b.GetLayerName(layer),'diameter_mm':.45,'drill_mm':.2,'outside_solder_pad':True})
finally:
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    (root/'exports/ground-lobe-connections.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
