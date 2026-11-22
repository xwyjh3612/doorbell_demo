"""Add a checked wide external-layer feed from the mux to modem bulk storage.

DC resistance is calculated from actual route length at 35 um copper. This is
not an IPC temperature or full load-drop qualification.
"""
from pathlib import Path
import json,math,shutil
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
shutil.copy2(file,'build/voice-v4-before-power-feed.kicad_pcb')
scope={'__file__':str(ROOT/'connect_ground_lobes.py')}
exec(compile((ROOT/'connect_ground_lobes.py').read_text(encoding='utf8').split('pairs =')[0],'checked_router','exec'),scope)
r=scope['r'];report=[];before={t.m_Uuid.AsString()for t in r.board.GetTracks()}
try:
    r.escapevia('MUX_POWER_FEED',('U10',2),diameter=.6,drill=.3,neck=.25)
    r.escapevia('MODEM_POWER_FEED',('C8',1),diameter=.6,drill=.3,neck=.4)
    r.route(('MUX_POWER_FEED',0),('MODEM_POWER_FEED',0),layer=p.B_Cu,width=.6,step=.1,bounds=(20,1,80,65))
    report.append({'connected':True,'layer':'B.Cu','trunk_width_mm':.6,'via_diameter_mm':.6,'drill_mm':.3})
except RuntimeError as e:report.append({'connected':False,'reason':str(e)})
added=[t for t in r.board.GetTracks()if t.m_Uuid.AsString()not in before]
length=0;resistance=0
for t in added:
    if isinstance(t,p.PCB_VIA):continue
    a,z=t.GetStart(),t.GetEnd();segment=math.dist((p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y)))
    length+=segment;resistance+=1.724e-8*(segment/1000)/(p.ToMM(t.GetWidth())/1000*35e-6)
    t.SetLocked(True)
p.SaveBoard(str(file),r.board)
(ROOT/'exports/modem-power-feed.json').write_text(json.dumps({'connections':report,'added_trace_length_mm':length,
    'trace_resistance_ohm_at_20C_35um_copper':resistance,'trace_drop_V_at_2A':2*resistance,
    'excludes':['via resistance','mux/PFET','connectors','temperature rise','transient droop'],
    'load_qualified':False},indent=2)+'\n',encoding='utf8')
print('Modem power feed:',report,'trace-only resistance',resistance)
