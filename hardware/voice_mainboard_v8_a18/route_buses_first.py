"""Reserve low-latency UART and audio bus connections before general routing."""
from pathlib import Path
import json
import pcbnew as p
from repair_connections import b,FILE,route,pos,layers
ROOT=Path(__file__).resolve().parent;fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,num):return next(d for d in fps[ref].Pads()if d.GetNumber()==str(num))
pairs=[(('U1',17),('U3',4)),(('U1',18),('U4',4)),(('U1',19),('U5',4)),
       (('U7',10),('U3',3)),(('U7',11),('U4',3)),(('U7',4),('U5',3)),
       (('U1',7),('Q1',3)),(('U1',15),('Q2',3)),(('U7',19),('Q1',1)),(('U7',23),('Q2',1)),
       (('U7',7),('U14',1)),(('U7',8),('U14',16)),(('U7',9),('U14',14)),
       (('U7',20),('J14',5)),(('U7',21),('J14',4)),(('U7',22),('J14',3)),
       (('U7',6),('J16',3)),(('U7',12),('J16',4)),
       (('U7',36),('J18',3)),(('U7',37),('J18',2)),
       (('U7',24),('U18',8)),(('U7',25),('U16',7)),(('U7',39),('U16',6)),
       (('U7',31),('Q7',1))]
report=[]
for a,z in pairs:
    pa,pz=pad(*a),pad(*z);assert pa.GetNetname()==pz.GetNetname(),(a,z)
    sl={i for i,l in enumerate(layers)if pa.IsOnLayer(l)};gl={i for i,l in enumerate(layers)if pz.IsOnLayer(l)}
    entry={'from':a,'to':z,'net':pa.GetNetname()}
    try:entry.update(route(pa.GetNetname(),pos(pa),pos(pz),sl,gl,width=.2),success=True)
    except RuntimeError as e:entry.update(success=False,reason=str(e))
    report.append(entry);p.SaveBoard(str(FILE),b);print(entry,flush=True)
for t in b.GetTracks():t.SetLocked(True)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
assert p.ExportSpecctraDSN(b,str(ROOT/'exports/buses-first.dsn'))
text=(ROOT/'exports/buses-first.dsn').read_text(encoding='utf-8')
power=['BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','ESP_3V3','MODEM_3V8','SYS_5V','VIN_PROTECTED']
fused=['VIN_DC','VIN_FUSED']
start=text.index('    (class kicad_default');end=text.index('      (circuit',start)
head=text[start:end]
import re
for name in power+fused:head=re.sub(r'(?<![\w])'+re.escape(name)+r'(?![\w])','',head)
text=text[:start]+head+text[end:];mark='  )\n  (wiring';assert mark in text
extra='    (class POWER '+' '.join(power)+' (circuit (use_via "Via[0-1]_600:300_um")) (rule (width 250) (clearance 200)))\n'
extra+='    (class FUSED_INPUT '+' '.join(fused)+' (circuit (use_via "Via[0-1]_600:300_um")) (rule (width 800) (clearance 200)))\n'
text=text.replace(mark,extra+mark,1)
(ROOT/'exports/buses-first.dsn').write_text(text,encoding='utf-8')
(ROOT/'exports/buses-first-routes.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
