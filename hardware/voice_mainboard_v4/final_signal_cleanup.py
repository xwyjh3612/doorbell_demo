"""Reroute amplifier enable around the EP drill and clear redundant tails."""
from pathlib import Path
import json,pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
scope={'__file__':str(ROOT/'connect_two_layers.py')}
exec(compile((ROOT/'connect_two_layers.py').read_text(encoding='utf8').split('d=json.loads')[0],'router','exec'),scope)
r=scope['r'];m=scope['m'];b=r.board;held=[];report=[]
for t in list(b.GetTracks()):
    if t.GetNetname()=='AMP_SD':b.Remove(t);held.append(t)
try:report.append({'net':'AMP_SD','connected':True,**m.route(r,('U14',4),('R61',2),width=.2,step=.05,bounds=(83,12,99,28))})
except RuntimeError as e:report.append({'net':'AMP_SD','connected':False,'reason':str(e)})
drc=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
tails={i['uuid']for v in drc['violations']if v['type']=='track_dangling'for i in v['items']}
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString()in tails and t.GetNetname()=='BAT_ALLOWED':b.Remove(t);held.append(t)
p.SaveBoard(str(file),b)
(ROOT/'exports/final-signal-cleanup.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(report)
