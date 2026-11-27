"""Short narrow pad necks into wider power paths; ordinary off-pad vias."""
from pathlib import Path
import json,sys
import pcbnew as p
ROOT=Path(__file__).resolve().parent
wrapper=(ROOT.parent/'voice_mainboard_v4/connect_ground_lobes.py').read_text(encoding='utf-8').split('pairs =')[0]
wrapper=wrapper.replace("file = ROOT / 'voice_mainboard_v4.kicad_pcb'", "file = ROOT / 'voice_mainboard_v8_a18.kicad_pcb'")
scope={'__file__':str(ROOT/'fanout_power.py')}
exec(compile(wrapper,'a18_pad_escape','exec'),scope)
r=scope['r']
import repair_connections as rc
rc.b=r.board
entries=[]
for ref,num in [('U18',2),('U18',3),('U18',6),('U15',4),('U15',7),('U17',2)]:
    name=f'{ref}_{num}_power';entry={'pad':[ref,num]}
    try:r.escapevia(name,(ref,num),diameter=.6,drill=.3,neck=.2);entry.update(success=True,via_mm=r.pos(r.virtual[name]))
    except RuntimeError as e:entry.update(success=False,reason=str(e))
    entries.append(entry);p.SaveBoard(str(rc.FILE),r.board)
for a,z,w in [(('U18_2_power',0),('U2',4),.6),(('U18_2_power',0),('U13',4),.6),
              (('U18_2_power',0),('C8',1),.6),(('Q6',2),('U18_3_power',0),.6),
              (('U15_7_power',0),('U18_6_power',0),.6),(('U15_7_power',0),('C65',1),.6),
              (('U15_7_power',0),('C66',1),.6),(('U15_4_power',0),('L4',1),.6),
              (('U17_2_power',0),('J23',2),.6)]:
    entry={'from':a,'to':z,'width_mm':w}
    try:
        pa,pz=r.pad(*a),r.pad(*z);assert pa.GetNetname()==pz.GetNetname()
        sl={i for i,l in enumerate(rc.layers)if not hasattr(pa,'IsOnLayer')or pa.IsOnLayer(l)}
        gl={i for i,l in enumerate(rc.layers)if not hasattr(pz,'IsOnLayer')or pz.IsOnLayer(l)}
        entry.update(rc.route(pa.GetNetname(),r.pos(pa),r.pos(pz),sl,gl,width=w),success=True)
    except (RuntimeError,StopIteration)as e:entry.update(success=False,reason=str(e))
    entries.append(entry);p.SaveBoard(str(rc.FILE),r.board)
    print(entry,flush=True)
for t in r.board.GetTracks():t.SetLocked(True)
r.board.BuildConnectivity();assert p.ZONE_FILLER(r.board).Fill(r.board.Zones());p.SaveBoard(str(rc.FILE),r.board)
assert p.ExportSpecctraDSN(r.board,str(ROOT/'exports/power-first.dsn'))
text=(ROOT/'exports/power-first.dsn').read_text(encoding='utf-8')
# Explicit classes because standalone pcbnew doesn't necessarily hydrate the
# project's net settings. Exact same net names; no pad assignment changes.
power=['BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','ESP_3V3','MODEM_3V8','SYS_5V','VIN_PROTECTED']
fused=['VIN_DC','VIN_FUSED']
start=text.index('    (class kicad_default');end=text.index('      (circuit',start)
head=text[start:end]
import re
for name in power+fused:head=re.sub(r'(?<![\w])'+re.escape(name)+r'(?![\w])','',head)
text=text[:start]+head+text[end:]
mark='  )\n  (wiring'
assert mark in text
extra='    (class POWER '+' '.join(power)+' (circuit (use_via "Via[0-1]_600:300_um")) (rule (width 250) (clearance 200)))\n'
extra+='    (class FUSED_INPUT '+' '.join(fused)+' (circuit (use_via "Via[0-1]_600:300_um")) (rule (width 800) (clearance 200)))\n'
text=text.replace(mark,extra+mark,1)
(ROOT/'exports/power-first.dsn').write_text(text,encoding='utf-8')
(ROOT/'exports/power-fanout.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
