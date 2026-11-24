"""Fan out control pins before constructing the high-current pours."""
from pathlib import Path
import json,sys,pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
base=p.LoadBoard(str(ROOT.parent/'voice_mainboard_v5/voice_mainboard_v5.kicad_pcb'))
baseids={t.m_Uuid.AsString() for t in base.GetTracks()}
b=p.LoadBoard(str(FILE));held=[]
clear={'SYS_5V','VIN_PROTECTED','BAT_SENSE_IN','BAT_BOOST_5V','CHG_CE','CHG_DISABLE_IO38','CHG_ACTIVE_N','UPS_FB','CHG_PROG','UPS_ISET'}
for t in list(b.GetTracks()):
    if t.GetNetname() in clear and t.m_Uuid.AsString() not in baseids:held.append(t);b.Remove(t)
p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
r,m=load();report=[]
for pair in [('U7',34),('U7',25)]:
    try:r.escapevia('ctrl_'+str(pair[1]),pair,diameter=.6,drill=.3,neck=.2);report.append({'pin':pair,'off_pad_via':True})
    except (RuntimeError,AssertionError) as e:report.append({'pin':pair,'off_pad_via':False,'error':str(e)})
for a,z in [(('U15',6),('R63',1)),(('U15',5),('R61',2)),(('R61',2),('R62',1)),
            (('U16',2),('R64',1)),(('U16',7),('R73',2)),(('U16',8),('R68',2)),
            (('Q7',3),('R68',2)),(('Q7',1),('R69',1)),(('Q7',1),('U7',34)),(('U16',7),('U7',25))]:
    aa,zz=r.pos(r.pad(*a)),r.pos(r.pad(*z));bounds=(max(.6,min(aa[0],zz[0])-5),max(.6,min(aa[1],zz[1])-5),min(99.4,max(aa[0],zz[0])+5),min(74.4,max(aa[1],zz[1])+5))
    try:
        try:r.route(a,z,width=.2,step=.05,bounds=bounds)
        except (RuntimeError,AssertionError):m.route(r,a,z,width=.2,step=.1,bounds=bounds)
        report.append({'from':a,'to':z,'routed':True})
    except (RuntimeError,AssertionError) as e:report.append({'from':a,'to':z,'routed':False,'error':str(e)})
    p.SaveBoard(str(FILE),r.board)
(ROOT/'exports/control-routing.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(report)
