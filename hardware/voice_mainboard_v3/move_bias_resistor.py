"""Give the reference bias resistor an unobstructed back-side exit."""
from pathlib import Path
import json,pcbnew as p
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
fp=next(f for f in b.GetFootprints()if f.GetReference()=='R42');fp.SetPosition(p.VECTOR2I(p.FromMM(4.5),p.FromMM(47)))
tracks=list(b.GetTracks());old=[]
for t in tracks:
    if t.GetNetname()=='UPS_REF_1V24':old.append(t);b.Remove(t)
d=json.loads((root/'design.json').read_text(encoding='utf8'))
for item in d['parts']:
    if item['ref']=='R42':item.update(x=4.5,y=47)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
progress=root/'exports/control-signal-routes.json'
if progress.exists():
    v=json.loads(progress.read_text(encoding='utf8'));v['branches']=[x for x in v['branches']if x['net']!='UPS_REF_1V24'];progress.write_text(json.dumps(v,indent=2)+'\n',encoding='utf8')
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
print('Bias resistor moved; reference routes must be rebuilt.')
