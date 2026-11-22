"""Reinforce the long protected-input trunk with a solid inner copper region.

The continuous In1 ground reference is unchanged. In2 uses 0.5oz copper;
the final voltage-drop review must measure real connected copper bottlenecks.
"""
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
held=list(b.Zones())
for z in held:
    if z.GetNetname()=='VIN_PROTECTED':b.Remove(z)
z=p.ZONE(b);z.SetLayer(p.In2_Cu);z.SetNetCode(b.FindNet('VIN_PROTECTED').GetNetCode())
z.SetLocalClearance(p.FromMM(.2));z.SetMinThickness(p.FromMM(.2));z.SetPadConnection(p.ZONE_CONNECTION_FULL);z.SetAssignedPriority(30);z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
poly=z.Outline();poly.NewOutline()
for x,y in [(8.5,22),(29,22),(29,27.5),(22.5,27.5),(22.5,53),(15,53),(15,29),(8.5,29)]:poly.Append(p.FromMM(x),p.FromMM(y))
b.Add(z);assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
print('Protected-input inner copper reinforcement filled; inspect bottlenecks before qualification')
