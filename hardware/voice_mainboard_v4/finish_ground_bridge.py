"""Join the final ground island at an existing via rather than a zone origin."""
from pathlib import Path
import json,math,pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
scope={'__file__':str(ROOT/'connect_two_layers.py')}
exec(compile((ROOT/'connect_two_layers.py').read_text(encoding='utf8').split('d=json.loads')[0],'router','exec'),scope)
r=scope['r'];m=scope['m'];b=r.board;report=[]
r.virtual['LAST_GND']=r.Endpoint('GND',(46,33.5))
vias=sorted([t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND'and math.dist(r.pos(t),(46,33.5))>1],key=lambda t:math.dist(r.pos(t),(46,33.5)))
for t in vias[:25]:
    xy=r.pos(t);r.virtual['GND_TARGET']=r.Endpoint('GND',xy)
    try:
        result=m.route(r,('LAST_GND',0),('GND_TARGET',0),width=.2,step=.05,bounds=(30,20,58,44))
        report.append({'target_mm':xy,'connected':True,**result});break
    except RuntimeError:continue
p.SaveBoard(str(file),b)
(ROOT/'exports/final-ground-bridge.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Final ground bridge:',report)
