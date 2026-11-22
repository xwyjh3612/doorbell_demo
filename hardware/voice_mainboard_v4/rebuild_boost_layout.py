"""Shorten the boost switch loop and put feedback parts outside that loop.

Only the selected boost neighborhood is released. Standard via drilling remains
0.3 mm. Copper widths are engineering inputs; load/transient qualification is
separate from native DRC.
"""
from pathlib import Path
import json,math
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
scope={'__file__':str(ROOT/'connect_ground_lobes.py')}
exec(compile((ROOT/'connect_ground_lobes.py').read_text(encoding='utf8').split('pairs =')[0],'checked_router','exec'),scope)
r=scope['r'];b=r.board;held=[];report=[]
for t in list(b.GetTracks()):
    remove=t.GetNetname()in ['UPS_SW','UPS_CBST','UPS_BOOST_FB']
    if t.GetNetname()in ['POWER_BUS','SYS_5V']:
        a,z=t.GetStart(),t.GetEnd()
        remove|=any(79<=p.ToMM(v.x)<=96 and 7<=p.ToMM(v.y)<=17 for v in [a,z])
    if remove:b.Remove(t);held.append(t)
fps={f.GetReference():f for f in b.GetFootprints()}
placements={'U9':(85,11.55,90),'C45':(85,14,0),'C42':(88.5,12.15,0),'R40':(80.3,9,270),'R41':(78,9,270)}
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
for ref,(x,y,angle)in placements.items():fps[ref].SetOrientationDegrees(angle);fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
# Synchronize all final placements with the authoritative native board.
for part in d['parts']:
    f=fps[part['ref']];part.update(x=p.ToMM(f.GetPosition().x),y=p.ToMM(f.GetPosition().y),angle=f.GetOrientationDegrees())
r.virtual['SW_EXIT']=r.Endpoint('UPS_SW',(85,9.85))
r.virtual['OUT_EXIT']=r.Endpoint('SYS_5V',(86.35,12.15))
tasks=[(('U9',5),('SW_EXIT',0),.25),(('SW_EXIT',0),('L3',2),.8),
       (('U9',7),('OUT_EXIT',0),.3),(('OUT_EXIT',0),('C42',1),.75),
       (('C42',1),('C43',1),.8),(('U9',1),('C45',1),.2),
       (('U9',7),('C45',2),.2),(('U9',3),('R40',2),.2),
       (('R40',2),('R41',1),.2),(('U9',2),('C41',1),.3),
       (('U9',4),('C41',1),.2),(('C41',1),('L3',1),.7)]
for a,z,width in tasks:
    try:r.route(a,z,width=width,step=.025,bounds=(76,1,98,19));report.append({'from':a,'to':z,'width_mm':width,'connected':True})
    except RuntimeError as e:report.append({'from':a,'to':z,'width_mm':width,'connected':False,'reason':str(e)})
for t in b.GetTracks():
    t.SetLocked(not isinstance(t,p.PCB_VIA)and p.ToMM(t.GetWidth())>=.3)
# Save only here; the next process reloads copper and rebuilds zone connectivity.
p.SaveBoard(str(file),b)
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'exports/boost-layout.json').write_text(json.dumps({'placements':placements,'connections':report,'load_qualified':False},indent=2)+'\n',encoding='utf8')
print('Boost connections:',sum(x['connected']for x in report),'/',len(report))
