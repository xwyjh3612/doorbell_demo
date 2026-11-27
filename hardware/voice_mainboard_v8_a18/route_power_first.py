"""Reserve actual critical supply/switch/feedback paths before ordinary signals."""
from pathlib import Path
import json, time
import pcbnew as p
from repair_connections import b,FILE,route,pos,layers
ROOT=Path(__file__).resolve().parent
fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,n):return next(d for d in fps[ref].Pads()if d.GetNumber()==str(n))
pairs=[
    (('U2',3),('L1',1),.8),
    (('U13',3),('L5',1),.6),
    (('U15',3),('L4',2),.8),
    (('U15',4),('L4',1),.8),
    (('L1',2),('U1',42),.8),
    (('U1',42),('U1',43),.8),
    (('U1',42),('C10',1),.4),
    (('U1',42),('C11',1),.25),
    (('L1',2),('C6',1),.6),
    (('L1',2),('C7',1),.6),
    (('L5',2),('U7',2),.6),
    (('L5',2),('C60',1),.4),
    (('U2',4),('C4',1),.4),
    (('U13',4),('C59',1),.4),
    (('U15',7),('C65',1),.8),
    (('U15',7),('C66',1),.6),
    (('U17',2),('J23',2),.8),
    (('U17',2),('U17',3),.6),
    (('J23',1),('L4',1),.8),
    (('J1',4),('F1',1),.8),
    (('F1',2),('Q6',3),.6),
    (('Q6',2),('U18',3),.6),
    (('U18',2),('U2',4),.6),
    (('U18',2),('U13',4),.6),
    (('U18',2),('C8',1),.6),
    (('U15',7),('U18',6),.6),
    (('U2',5),('R3',1),.2),
    (('U13',5),('R60',1),.2),
    (('U15',5),('R61',2),.2),
    (('U15',5),('R62',1),.2),
]
report=[]
for a,z,width in pairs:
    pa,pz=pad(*a),pad(*z);net=pa.GetNetname();assert net==pz.GetNetname(),(a,z)
    sl={i for i,l in enumerate(layers)if pa.IsOnLayer(l)};gl={i for i,l in enumerate(layers)if pz.IsOnLayer(l)}
    entry={'net':net,'from':a,'to':z,'width_mm':width};started=time.monotonic()
    try:entry.update(route(net,pos(pa),pos(pz),sl,gl,width=width),success=True)
    except RuntimeError as e:entry.update(success=False,reason=str(e))
    report.append(entry);p.SaveBoard(str(FILE),b)
    print(net,a,z,width,entry['success'],entry.get('reason',''),round(time.monotonic()-started,1),flush=True)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
assert p.ExportSpecctraDSN(b,str(ROOT/'exports/power-first.dsn'))
text=(ROOT/'exports/power-first.dsn').read_text(encoding='utf-8')
import re
text,n=re.subn(r'(\(class POWER\s+.*?\(rule\s+\(width )800(\))',lambda m:m[1]+'250'+m[2],text,flags=re.S);assert n==1
text=text.replace('      VIN_DC VIN_FUSED VIN_PROTECTED','      VIN_PROTECTED')
text=text.replace('    (class RF RF_ANT RF_FEED','    (class FUSED_INPUT VIN_DC VIN_FUSED (circuit (use_via "Via[0-1]_600:300_um")) (rule (width 800) (clearance 200)))\n    (class RF RF_ANT RF_FEED')
(ROOT/'exports/power-first.dsn').write_text(text,encoding='utf-8')
(ROOT/'exports/power-first-routes.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
