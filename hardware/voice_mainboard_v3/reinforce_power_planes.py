"""Reinforce shared current paths while retaining continuous In1 ground.

Outer 1oz copper supplements existing inner 0.5oz trunks. Zones obey every
foreign-net clearance; current/temperature and actual bottlenecks are audited
separately and remain subject to physical load tests.
"""
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
held=list(b.Zones())
for z in held:
    if z.GetNetname()in ['POWER_BUS','POWER_REG_5V']:b.Remove(z)
def zone(net,outline,priority):
    z=p.ZONE(b);z.SetLayer(p.B_Cu);z.SetNetCode(b.FindNet(net).GetNetCode());z.SetLocalClearance(p.FromMM(.2));z.SetMinThickness(p.FromMM(.2));z.SetPadConnection(p.ZONE_CONNECTION_FULL);z.SetAssignedPriority(priority);z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    poly=z.Outline();poly.NewOutline()
    for x,y in outline:poly.Append(p.FromMM(x),p.FromMM(y))
    b.Add(z)
zone('POWER_BUS',[(11.5,22),(24,22),(29,13),(29,.5),(45,.5),(45,17),(30,25),(29,39),(16,39),(16,28),(11.5,28)],40)
zone('POWER_REG_5V',[(15,23),(17,23),(17,45.5),(20,45.5),(20,62),(28,62),(28,73.5),(19,73.5),(19,65),(16,65),(16,49),(15,49)],35)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
print('Reinforced shared supply and UPS output with outer 1oz copper; In1 ground retained')
