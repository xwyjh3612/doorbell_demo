"""Clear a conflicting I2S detour and finish the local boost power escape."""
from pathlib import Path
import json,pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
scope={'__file__':str(ROOT/'connect_ground_lobes.py')}
exec(compile((ROOT/'connect_ground_lobes.py').read_text(encoding='utf8').split('pairs =')[0],'router','exec'),scope)
r=scope['r'];b=r.board;held=[];report=[]
for t in list(b.GetTracks()):
    remove=t.GetNetname()in ['I2S_SPK_WS16','UPS_BOOST_FB']
    if t.GetNetname()=='POWER_BUS':
        a,z=t.GetStart(),t.GetEnd();remove|=any(79<=p.ToMM(v.x)<=87 and 9<=p.ToMM(v.y)<=15 for v in [a,z])
    if remove:b.Remove(t);held.append(t)
fps={f.GetReference():f for f in b.GetFootprints()}
for ref,x in [('R40',80.3),('R41',78)]:fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(9)))
r.virtual['OUT_EXIT']=r.Endpoint('SYS_5V',(86.35,12.15))
r.virtual['VIN_EXIT']=r.Endpoint('POWER_BUS',(83.2,11.8))
tasks=[(('U9',7),('OUT_EXIT',0),.3),(('OUT_EXIT',0),('C42',1),.75),
       (('U9',1),('C45',1),.2),(('U9',3),('R40',2),.2),
       (('R40',2),('R41',1),.2),(('U9',2),('VIN_EXIT',0),.25),
       (('VIN_EXIT',0),('C41',1),.55),(('U9',4),('C41',1),.2),
       (('C41',1),('L3',1),.7)]
for a,z,width in tasks:
    try:r.route(a,z,width=width,step=.025,bounds=(75,1,98,19));report.append({'from':a,'to':z,'width_mm':width,'connected':True})
    except RuntimeError as e:report.append({'from':a,'to':z,'connected':False,'reason':str(e)})
for t in b.GetTracks():t.SetLocked(not isinstance(t,p.PCB_VIA)and p.ToMM(t.GetWidth())>=.25)
p.SaveBoard(str(file),b)
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
for part in d['parts']:
    f=fps[part['ref']];part.update(x=p.ToMM(f.GetPosition().x),y=p.ToMM(f.GetPosition().y),angle=f.GetOrientationDegrees())
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'exports/boost-escape.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Final local boost connections:',sum(x['connected']for x in report),'/',len(report))
