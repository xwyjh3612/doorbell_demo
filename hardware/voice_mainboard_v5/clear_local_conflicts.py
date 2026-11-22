"""Release conflicting copper, retain all required pads, and free ESP supply space."""
from pathlib import Path
import json,pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
b=p.LoadBoard(str(file))
d=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
bad={it['uuid'] for v in d['violations'] for it in v['items']}
data=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
fp=next(f for f in b.GetFootprints() if f.GetReference()=='R57')
fp.SetPosition(p.VECTOR2I(p.FromMM(7),p.FromMM(15.8)))
for q in data['parts']:
    if q['ref']=='R57':q.update(x=7,y=15.8)
held=[]
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString() in bad or t.GetNetname() in ['ESP_3V3','ESP_EN']:
        held.append(t);b.Remove(t)
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(file),b)
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for t in held:t.thisown=False
print('Released',len(held),'conflicting/tail/supply items; required pads retained; ESP supply must be rerouted')
