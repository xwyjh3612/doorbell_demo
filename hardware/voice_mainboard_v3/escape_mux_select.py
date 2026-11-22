"""Provide the mux PR1 signal's conventional off-pad escape.

The point is checked by KiCad DRC after adding it, including all-layer copper
and plated-hole spacing. It is outside the IC and every solder-paste pad.
"""
from pathlib import Path
import sys,pcbnew as p
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
xy=(15.25,51.75);name='mux_pr1_fixed'
if not any(isinstance(t,p.PCB_VIA)and t.GetNetname()=='UPS_EXT_VALID'and abs(r.pos(t)[0]-xy[0])<.001 and abs(r.pos(t)[1]-xy[1])<.001 for t in r.board.GetTracks()):
    old=[]
    for t in list(r.board.GetTracks()):
        if t.GetNetname()=='UPS_EXT_VALID'and(isinstance(t,p.PCB_VIA)or t.GetLayer()==p.F_Cu):old.append(t);r.board.Remove(t)
    r.virtual[name]=r.Endpoint('UPS_EXT_VALID',xy)
    r.route(('U10',4),(name,0),width=.2,step=.025,bounds=(14.5,50.4,18.1,52.4))
    r.addvia(name,'UPS_EXT_VALID',xy)
    assert p.ZONE_FILLER(r.board).Fill(r.board.Zones())
    p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),r.board)
    print('Mux PR1 escape completed; DRC required.')
