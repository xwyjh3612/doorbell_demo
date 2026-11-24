"""Move the pulldown out of a trapped ground pocket, then reconnect its gate."""
from pathlib import Path
import json,math,pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
b=p.LoadBoard(str(FILE));d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
f=next(f for f in b.GetFootprints() if f.GetReference()=='R69');f.SetPosition(p.VECTOR2I(p.FromMM(54),p.FromMM(52)))
next(q for q in d['parts'] if q['ref']=='R69')['x']=54
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8');p.SaveBoard(str(FILE),b)
r,m=load();gate=r.pad('Q7',1)
vias=sorted([t for t in r.board.GetTracks() if isinstance(t,p.PCB_VIA) and t.GetNetname()==gate.GetNetname()],key=lambda t:math.dist(r.pos(t),r.pos(gate)))
assert vias;r.virtual['gate_via']=vias[0]
m.route(r,('gate_via',0),('R69',1),width=.2,step=.1,bounds=(42,44,59,57))
r.board.BuildConnectivity();assert p.ZONE_FILLER(r.board).Fill(r.board.Zones());p.SaveBoard(str(FILE),r.board)
