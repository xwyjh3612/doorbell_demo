from pathlib import Path
import math,json,pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
b=p.LoadBoard(str(FILE));held=[]
for t in list(b.GetTracks()):
    if t.GetNetname() in ['CHG_CE','CHG_FULL_N']:held.append(t);b.Remove(t)
p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
r,m=load();report=[]
for ref,n in [('U16',7),('U16',6),('U7',39)]:
    try:r.escapevia(ref+'_ctrl',(ref,n),diameter=.6,drill=.3,neck=.2)
    except (RuntimeError,AssertionError) as e:print('fanout failed',ref,e,flush=True)
    p.SaveBoard(str(FILE),r.board)
def nearest(ref,n,name):
    pd=r.pad(ref,n);pt=r.pos(pd)
    vs=sorted([t for t in r.board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()==pd.GetNetname()],key=lambda t:math.dist(pt,r.pos(t)))
    assert vs and math.dist(pt,r.pos(vs[0]))<5,(ref,n)
    r.virtual[name]=vs[0];return name,0
u=nearest('U16',7,'chg_start');g=nearest('Q7',1,'gate_start')
a=nearest('U7',25,'chg_end');z=nearest('U7',34,'gate_end')
f=nearest('U16',6,'full_start');fe=nearest('U7',39,'full_end')
for aa,zz in [(u,a),(g,z),(f,fe),(u,('R73',2)),(g,('R69',1)),(f,('R74',2)),(('U16',8),('R68',2)),(('Q7',3),('R68',2))]:
    try:m.route(r,aa,zz,width=.2,step=.1,bounds=(.6,.6,99.4,74.4));report.append({'from':aa,'to':zz,'routed':True})
    except (RuntimeError,AssertionError) as e:report.append({'from':aa,'to':zz,'routed':False,'reason':str(e)})
    p.SaveBoard(str(FILE),r.board)
(ROOT/'exports/late-control-routing.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(report)
