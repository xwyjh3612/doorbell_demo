"""Add two ground references and a local modem VBAT reservoir area.

Other long power trunks still need copper/current review. Ground continuity is
checked after filling, rather than presumed from the zone outline.
"""
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v4.kicad_pcb';b=p.LoadBoard(str(file))
assert b.GetCopperLayerCount()==2
existing=[z for z in b.Zones() if not z.GetIsRuleArea()]
if existing:
    assert len(existing)==3 and sorted(z.GetNetname() for z in existing)==['GND','GND','POWER_BUS']
def add(net,layer,outline,priority=0):
    z=p.ZONE(b);z.SetLayer(layer);z.SetNet(b.FindNet(net));z.SetLocalClearance(p.FromMM(.2))
    z.SetMinThickness(p.FromMM(.2));z.SetAssignedPriority(priority)
    z.SetPadConnection(p.ZONE_CONNECTION_FULL)
    poly=z.Outline();poly.NewOutline()
    for x,y in outline:poly.Append(p.FromMM(x),p.FromMM(y))
    b.Add(z)
if not existing:
    for layer in [p.F_Cu,p.B_Cu]:add('GND',layer,[(.5,.5),(99.5,.5),(99.5,74.5),(.5,74.5)])
    add('POWER_BUS',p.F_Cu,[(54.5,4.5),(65,4.5),(65,18.15),(61.8,18.15),(61.8,13),(54.5,13)],20)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(file),b)
print('Filled two-layer ground and local modem reservoir copper')
