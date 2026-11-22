"""Release output fanout to reserve adjacent VIN2/MODE exits first.

Only POWER_REG_5V copper is reworked; RF/USB/modem regulators stay unchanged.
"""
from pathlib import Path
import json,pcbnew as p
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
alltracks=list(b.GetTracks());removed=[]
for t in alltracks:
    if t.GetNetname()=='POWER_REG_5V':removed.append(t);b.Remove(t)
progress=root/'exports/power-trunks.json';d=json.loads(progress.read_text(encoding='utf8'))
refs={'U10/2','U10/7','C53/1','C48/1'}
d['branches']=[x for x in d['branches']if x['from'][0]+'/'+str(x['from'][1])not in refs and x['to'][0]+'/'+str(x['to'][1])not in refs]
d['escape_vias']={key:value for key,value in d['escape_vias'].items()if key not in refs}
d['complete']=False;progress.write_text(json.dumps(d,indent=2)+'\n',encoding='utf8')
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
print('Released mux output fanout:',len(removed),'copper items')
