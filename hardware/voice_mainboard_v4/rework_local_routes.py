"""Localized routing rework with a saved backup, then independent native DRC.

Clear only named nets and native-reported dangling track segments. Updated
placement is recorded in design.json; no firmware or V3 files are touched.
"""
from pathlib import Path
import types,sys,json,math,shutil
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v4.kicad_pcb'
backup=Path('build/voice-v4-before-local-rework.kicad_pcb')
if not backup.exists():shutil.copy2(file,backup)
loader=(ROOT/'connect_ground_lobes.py').read_text(encoding='utf8').split('pairs =')[0]
scope={'__file__':str(ROOT/'connect_ground_lobes.py')};exec(compile(loader,'checked_router','exec'),scope);r=scope['r']
b=r.board;held=[];report=[]
clear_nets=['AMP_GAIN','AMP_SD','BAT_ALLOWED','MODEM_1V8','M_RX_1V8']
for t in list(b.GetTracks()):
    if t.GetNetname()in clear_nets:held.append(t);b.Remove(t)
drc=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
tails={it['uuid']for v in drc['violations']if v['type']=='track_dangling'for it in v['items']}
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString()in tails:held.append(t);b.Remove(t)
fps={f.GetReference():f for f in b.GetFootprints()}
placements={'R61':(88,22,0),'R62':(88,16,0),'C18':(51,31,180)}
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
for ref,(x,y,angle)in placements.items():
    fps[ref].SetOrientationDegrees(angle);fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
    for part in d['parts']:
        if part['ref']==ref:part.update(x=x,y=y,angle=angle)
def route_pair(a,z,net=None):
    net=net or r.pad(*a).GetNetname();src,goal=r.pos(r.pad(*a)),r.pos(r.pad(*z))
    bounds=(max(.7,min(src[0],goal[0])-4),max(.7,min(src[1],goal[1])-4),min(99.3,max(src[0],goal[0])+4),min(74.3,max(src[1],goal[1])+4))
    try:
        r.route(a,z,width=.2,step=.05,bounds=bounds)
        report.append({'net':net,'from':a,'to':z,'connected':True,'method':'front'})
        return True
    except RuntimeError:pass
    try:
        av='ESC_A_'+str(len(report));zv='ESC_Z_'+str(len(report))
        r.escapevia(av,a);r.escapevia(zv,z)
        r.route((av,0),(zv,0),layer=p.B_Cu,width=.2,step=.05,bounds=bounds)
        report.append({'net':net,'from':a,'to':z,'connected':True,'method':'back_escape'})
        return True
    except RuntimeError as error:
        report.append({'net':net,'from':a,'to':z,'connected':False,'reason':str(error)})
        return False
    finally:p.SaveBoard(str(file),b)
# First free the blocked fine-pitch inputs, then refill the released nets.
route_pair(('U10',4),('R34',2))
route_pair(('U9',2),('C41',1))
route_pair(('U9',3),('R40',2))
route_pair(('U14',4),('R61',2))
route_pair(('U14',2),('R62',1))
route_pair(('U3',4),('U1',17))
for net in ['BAT_ALLOWED','MODEM_1V8']:
    endpoints=[(f.GetReference(),pd.GetNumber())for f in b.GetFootprints()for pd in f.Pads()if pd.GetNetname()==net]
    joined=[endpoints.pop(0)]
    while endpoints:
        a,z=min(((a,z)for a in joined for z in endpoints),key=lambda pair:math.dist(r.pos(r.pad(*pair[0])),r.pos(r.pad(*pair[1]))))
        route_pair(a,z);joined.append(z);endpoints.remove(z)
route_pair(('R61',1),('C62',1))
route_pair(('R62',2),('U14',3))
for i,pair in enumerate([('U14',17),('U1',95),('C18',2)]):
    try:
        r.escapevia('GND_LOCAL_'+str(i),pair)
        report.append({'from':pair,'net':'GND','connected':True,'method':'off_pad_via'})
    except RuntimeError as e:report.append({'from':pair,'net':'GND','connected':False,'reason':str(e)})
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'exports/local-rework.json').write_text(json.dumps({'removed_track_count':len(held),'placements':placements,'connections':report},indent=2)+'\n',encoding='utf8')
print('Local connections:',sum(x['connected']for x in report),'/',len(report))
