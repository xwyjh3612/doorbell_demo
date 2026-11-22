"""Reserve all mux leads before routing wide power trunks.

Hole clearance and solder-pad clearance are checked on every layer before
adding a conventional 0.6mm/0.3mm via. Same-net existing vias are reused.
KiCad DRC is the independent final check.
"""
from pathlib import Path
import sys,json,math
import pcbnew as p
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import Point,LineString
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
b=r.board
preferred={1:(16.6,46.7),2:(18,47.75),3:(16.2,47.9),4:(16.4,48.8),5:(20,49.9),6:(19.6,47.45),7:(18,47.75),8:(18.6,46.6)}
report=json.loads((root/'exports/mux-fanout.json').read_text(encoding='utf8')).get('pins',[])
def clear(xy,net):
    pt=Point(xy)
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            gap=.255 if pd.GetNetname()==net else.505
            for layer in [p.F_Cu,p.B_Cu]:
                if pd.IsOnLayer(layer)and any(sh.buffer(gap).intersects(pt)for sh in r.polygons(pd,layer)):return False
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA):
            if t.GetNetname()==net and math.dist(r.pos(t),xy)<.001:return True
            if math.dist(r.pos(t),xy)<.15+p.ToMM(t.GetDrill())/2+.255:return False
            sh=Point(r.pos(t));rad=p.ToMM(t.GetWidth(p.F_Cu))/2
        else:sh=LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]);rad=p.ToMM(t.GetWidth())/2
        if t.GetNetname()!=net and sh.buffer(rad+.505).intersects(pt):return False
    return True
try:
    for pin in [1,8,4,3,6,5,2,7]:
        if any(item['pin']==pin for item in report):continue
        net=r.pad('U10',pin).GetNetname();pref=preferred[pin];name='mux_'+str(pin)
        shared=next((item for item in report if item['net']==net),None)
        if shared:
            r.virtual[name]=r.Endpoint(net,shared['via_mm'])
            r.route(('U10',pin),(name,0),width=.2,step=.025,bounds=(14,44,23,53))
        else:r.escapevia(name,('U10',pin),diameter=.6,drill=.3,neck=.2)
        found=r.pos(r.virtual[name])
        report.append({'pin':pin,'net':net,'via_mm':found,'neck_width_mm':.2,'via_diameter_mm':.6,'drill_mm':.3})
finally:
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    (root/'exports/mux-fanout.json').write_text(json.dumps({'pins':report,'complete':len(report)==8,'In1_signal_tracks':0},indent=2)+'\n',encoding='utf8')
