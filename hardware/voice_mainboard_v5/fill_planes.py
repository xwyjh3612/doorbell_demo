"""Fill front/back ground and short modem supply copper; obey reserve keepout."""
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
b=p.LoadBoard(str(file))


def add(net,layer,points,priority=0):
    z=p.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(b.FindNet(net))
    z.SetLocalClearance(p.FromMM(.2))
    z.SetMinThickness(p.FromMM(.2))
    z.SetAssignedPriority(priority)
    z.SetPadConnection(p.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    poly=z.Outline();poly.NewOutline()
    for x,y in points:poly.Append(p.FromMM(x),p.FromMM(y))
    b.Add(z)


if not any(not z.GetIsRuleArea() for z in b.Zones()):
    for layer in [p.F_Cu,p.B_Cu]:add('GND',layer,[(.5,.5),(99.5,.5),(99.5,74.5),(.5,74.5)])
    add('MODEM_3V8',p.F_Cu,[(59,13.5),(70.5,13.5),(70.5,16.1),(64.5,16.1),(64.5,18.0),(61.8,18.0),(61.8,16.1),(59,16.1)],20)
for zone in b.Zones():
    if not zone.GetIsRuleArea():
        zone.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(file),b)
print('Filled V5 ground and modem reservoir planes')
