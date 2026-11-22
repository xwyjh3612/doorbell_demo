"""Route the local switching loop first, before the remaining signal router.

Use the actual KiCad pad coordinates and collision-checked paths. This is a
geometry check, not a substitute for a converter transient/thermal test.
"""
from pathlib import Path
import json,sys
import pcbnew as p
sys.argv=[sys.argv[0],str(Path(__file__).resolve().parent/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
b=r.board
root=Path(__file__).resolve().parent
report=[]
def run(a,z,w=.2,layer=p.F_Cu):
    r.route(a,z,width=w,layer=layer,bounds=(2.1,43.3,30.5,73.8),step=.05)
    report.append({'from':a,'to':z,'width_mm':w,'layer':b.GetLayerName(layer)})
try:
    # SW exits to the left through a short neck, widening clear of RNS pads.
    r.virtual['sw_land']=r.Endpoint('UPS_SW',(16.0,57.0))
    run(('U9',5),('sw_land',0),.25)
    run(('sw_land',0),('L3',2),1.0)
    # VIN has a narrow package lead only; the route widens outside that lead.
    r.virtual['vin_land']=r.Endpoint('BAT_SENSE_IN',(16.4,58.7))
    run(('U9',4),('vin_land',0),.2)
    run(('vin_land',0),('C41',1),.7)
    run(('C41',1),('J2',1),1.0)
    run(('L3',1),('J2',1),1.2)
    run(('L3',1),('C40',1),.8)
    run(('U9',1),('C45',1),.2)
    run(('U9',5),('C45',2),.25)
    run(('U9',7),('C42',1),.25)
    run(('C42',1),('C43',1),.8)
    run(('C43',1),('C44',1),.8)
    run(('U9',6),('C42',2),.25)
    # Short off-pad vias return to the internal plane, instead of a long
    # perimeter ground trace around components.
    for ref,pin in [('U9',6),('C41',2),('C42',2)]:
        r.escapevia('gnd_'+ref,(ref,pin),neck=.25)
    # Low-current charger input/BAT; separated from the load path at the cell.
    run(('U8',4),('C38',1),.35)
    run(('U8',5),('C39',1),.35)
    run(('U8',5),('J2',1),.4)
finally:
    b.BuildConnectivity()
    assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    (root/'exports/ups-local-routes.json').write_text(json.dumps({'branches':report,'completed':len(report)==16,'hardware_validated':False},indent=2)+'\n',encoding='utf8')
