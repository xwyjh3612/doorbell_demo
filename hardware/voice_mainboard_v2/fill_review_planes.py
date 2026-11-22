"""Add solid ground reference layers and the local modem VBAT copper area.

Experimental review geometry: manufacturing/impedance/thermal approval remains
separate. CLI DRC is always run after filling.
"""
from pathlib import Path
import sys
import pcbnew as pcb

def fill(board):
    def zone(net,layer,outline,priority=0):
        z=pcb.ZONE(board);z.SetLayer(layer)
        z.SetNetCode(board.FindNet(net).GetNetCode())
        z.SetLocalClearance(pcb.FromMM(.2));z.SetMinThickness(pcb.FromMM(.2))
        z.SetPadConnection(pcb.ZONE_CONNECTION_FULL)
        z.SetAssignedPriority(priority)
        poly=z.Outline();poly.NewOutline()
        for x,y in outline:poly.Append(pcb.FromMM(x),pcb.FromMM(y))
        board.Add(z)
    for layer in [pcb.F_Cu,pcb.In1_Cu,pcb.In2_Cu,pcb.B_Cu]:
        zone('GND',layer,[(.5,.5),(99.5,.5),(99.5,74.5),(.5,74.5)])
    zone('MODEM_3V8',pcb.F_Cu,[(53.8,.5),(85.3,.5),(85.3,8.5),(77.8,8.5),(77.8,18.6),(53.8,18.6)],20)
    board.BuildConnectivity()
    assert pcb.ZONE_FILLER(board).Fill(board.Zones()),'Zone fill failed'

if __name__=='__main__':
    source=Path(sys.argv[1]);target=Path(sys.argv[2])
    board=pcb.LoadBoard(str(source));fill(board);pcb.SaveBoard(str(target),board)
    print('Filled ground references and modem VBAT area:',target)
