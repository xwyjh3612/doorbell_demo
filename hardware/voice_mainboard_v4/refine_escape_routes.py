"""Release enclosing signal loops and reconnect the fine-pitch breakout pads."""
from pathlib import Path
import json,pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
loader=(ROOT/'rework_local_routes.py').read_text(encoding='utf8')
loader=loader[loader.index('loader=(ROOT/'):loader.index('# First free')]
# Use routing helpers without replaying the previous placement/net clearing.
helper=loader[:loader.index('clear_nets=')]
scope={'__file__':str(ROOT/'refine_escape_routes.py'),'ROOT':ROOT,'file':file,'p':p,'json':json,'math':__import__('math')}
exec(compile(helper,'helpers','exec'),scope)
r=scope['r'];b=r.board;held=[];report=[]
old=p.LoadBoard('build/voice-v4-before-local-rework.kicad_pcb')
for t in list(b.GetTracks()):
    if t.GetNetname()in ['MODEM_1V8','M_TX_1V8','MODEM_NETLIGHT','AMP_GAIN','AMP_SD','UPS_SW']:
        b.Remove(t);held.append(t)
    elif t.GetNetname()=='POWER_BUS'and t.GetLayer()==p.F_Cu:
        a,z=t.GetStart(),t.GetEnd()
        if all(83<=p.ToMM(v.x)<=87 and 9<=p.ToMM(v.y)<=11 for v in [a,z]):b.Remove(t);held.append(t)
# Restore the previously connected 1.8V distribution before a small cap move.
for t in old.GetTracks():
    if t.GetNetname()!='MODEM_1V8':continue
    if isinstance(t,p.PCB_VIA):
        q=p.PCB_VIA(b);q.SetPosition(t.GetPosition());q.SetWidth(t.GetWidth(p.F_Cu));q.SetDrill(t.GetDrill());q.SetViaType(p.VIATYPE_THROUGH);q.SetLayerPair(p.F_Cu,p.B_Cu)
    else:
        q=p.PCB_TRACK(b);q.SetStart(t.GetStart());q.SetEnd(t.GetEnd());q.SetWidth(t.GetWidth());q.SetLayer(t.GetLayer())
    q.SetNetCode(b.FindNet('MODEM_1V8').GetNetCode());b.Add(q);held.append(q)
fps={f.GetReference():f for f in b.GetFootprints()}
placements={'R61':(92,23,180),'R62':(87,18.3,180),'C18':(51,29,0)}
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
for ref,(x,y,angle)in placements.items():
    fps[ref].SetOrientationDegrees(angle);fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
    for part in d['parts']:
        if part['ref']==ref:part.update(x=x,y=y,angle=angle)
# Previous helper defines route_pair with globals referring to the current board.
functions=loader[loader.index('def route_pair'):]
scope.update(r=r,b=b,report=report)
exec(compile(functions,'route_pair','exec'),scope);route_pair=scope['route_pair']
r.virtual['C18_OLD']=r.Endpoint('MODEM_1V8',(50.225,31))
try:
    r.route(('C18',1),('C18_OLD',0),width=.2,step=.025,bounds=(47,26,54,34))
    report.append({'net':'MODEM_1V8','connected':True})
except RuntimeError as e:report.append({'net':'MODEM_1V8','connected':False,'reason':str(e)})
for pair in [('C18',2),('U1',95)]:
    try:r.escapevia('LOCAL_GND_'+pair[0],pair);report.append({'net':'GND','from':pair,'connected':True})
    except RuntimeError as e:report.append({'net':'GND','from':pair,'connected':False,'reason':str(e)})
route_pair(('U3',4),('U1',17))
route_pair(('U4',4),('U1',18))
route_pair(('U1',16),('TP3',1))
route_pair(('U14',4),('R61',2))
route_pair(('U14',2),('R62',1))
route_pair(('R62',2),('U14',3))
route_pair(('R61',1),('U14',7))
# Short switch-current path; do not keep autorouter signal-size loops around FB.
r.virtual['SW_NECK']=r.Endpoint('UPS_SW',(82.9,11.5))
try:
    r.route(('U9',5),('SW_NECK',0),width=.2,step=.025,bounds=(78,6,92,16))
    r.route(('SW_NECK',0),('L3',2),width=.75,step=.04,bounds=(78,3,92,16))
    report.append({'net':'UPS_SW','connected':True,'neck_mm':.2,'trunk_mm':.75})
except RuntimeError as e:report.append({'net':'UPS_SW','connected':False,'reason':str(e)})
route_pair(('U9',3),('R40',2))
route_pair(('U9',2),('C41',1))
route_pair(('U9',4),('C41',1))
# Use the existing two source-isolation vias for the remaining control gap.
for name,xy in [('BAT_A',(40.4,50.5)),('BAT_Z',(46,48.4))]:r.virtual[name]=r.Endpoint('BAT_ALLOWED',xy)
try:
    r.route(('BAT_A',0),('BAT_Z',0),layer=p.B_Cu,width=.2,step=.05,bounds=(25,37,56,68))
    report.append({'net':'BAT_ALLOWED','connected':True})
except RuntimeError as e:report.append({'net':'BAT_ALLOWED','connected':False,'reason':str(e)})
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'exports/escape-refinement.json').write_text(json.dumps({'placements':placements,'connections':report},indent=2)+'\n',encoding='utf8')
print('Refined escapes:',sum(q['connected']for q in report),'/',len(report))
