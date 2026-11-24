"""Add separated high-current copper areas and ordinary off-pad connections.

These geometry checks do not establish allowable load, hot resistance or EMI.
"""
from pathlib import Path
import json,pcbnew as p
from route_support import load
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
r=load();b=r.board
zones=[
('BAT_SENSE_IN',p.F_Cu,20,[(10,60),(28,60),(30.4,64.5),(30.4,68),(10,68)]),
('CELL_NEG',p.F_Cu,30,[(10,65.7),(14.5,65.7),(15.5,63.95),(18.3,63.95),(18.3,65.7),(15,67.8),(10,67.8)]),
('BAT_BOOST_5V',p.F_Cu,30,[(34.3,61),(46,61),(46,67),(57,67),(57,62.6),(59,62.6),(59,72),(30.5,72),(30.5,67.2),(34.3,67.2)]),
('VIN_PROTECTED',p.B_Cu,20,[(24,38),(44,38),(44,60),(24,60)]),
('VIN_PROTECTED',p.F_Cu,40,[(39,48),(47,48),(47,57),(55,60),(55,65),(50,65),(41,58)]),
('SYS_5V',p.B_Cu,20,[(46,9),(53.2,9),(53.2,69),(46,69)]),
('MODEM_3V8',p.F_Cu,20,[(59,13.5),(70.5,13.5),(70.5,16.1),(64.5,16.1),(64.5,18),(61.8,18),(61.8,16.1),(59,16.1)])]
for net,layer,priority,pts in zones:
    if any(z.GetNetname()==net and z.GetLayer()==layer and not z.GetIsRuleArea() for z in b.Zones()):continue
    z=p.ZONE(b);z.SetNet(b.FindNet(net));z.SetLayer(layer);z.SetLocalClearance(p.FromMM(.2));z.SetMinThickness(p.FromMM(.2))
    z.SetAssignedPriority(priority);z.SetPadConnection(p.ZONE_CONNECTION_FULL);z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    z.Outline().NewOutline()
    for x,y in pts:z.Outline().Append(p.FromMM(x),p.FromMM(y))
    b.Add(z)
report=[]
for ref,n,w in [('Q6',2,.5),('C67',1,.5),('U18',2,.25),('C72',1,.5),('C4',1,.5),('U15',9,.4),('U16',9,.4),('U17',4,.3),('U17',5,.3)]:
    try:r.escapevia('pwr_'+ref+'_'+str(n),(ref,n),diameter=.6,drill=.3,neck=w);report.append({'pad':[ref,n],'via':True,'neck_mm':w})
    except (RuntimeError,AssertionError) as e:report.append({'pad':[ref,n],'via':False,'reason':str(e)})
for a,z,w in [(('U18',2),('U18',7),.2),(('U18',6),('C73',1),.3)]:
    try:r.route(a,z,width=w,step=.05,bounds=(48,60,60,70))
    except (RuntimeError,AssertionError) as e:report.append({'from':a,'to':z,'routed':False,'reason':str(e)})
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'exports/power-copper.json').write_text(json.dumps({'zones':[(n,b.GetLayerName(l),pr,pts) for n,l,pr,pts in zones],'connections':report,'2A_load_qualified':False},indent=2)+'\n',encoding='utf8')
print(report)
