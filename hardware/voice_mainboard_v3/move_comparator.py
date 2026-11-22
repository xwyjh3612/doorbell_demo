"""Move the slow back-side comparator away from the power-mux escape area."""
from pathlib import Path
import pcbnew as p,json
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
fp=next(f for f in b.GetFootprints()if f.GetReference()=='U11')
signals={pd.GetNetname()for pd in fp.Pads()if pd.GetNetname()!='GND'}
items=list(b.GetTracks());removed=[]
for t in items:
    if t.GetNetname()in signals:removed.append(t);b.Remove(t)
fp.SetPosition(p.VECTOR2I(p.FromMM(15),p.FromMM(66)))
d=json.loads((root/'design.json').read_text(encoding='utf8'))
for item in d['parts']:
    if item['ref']=='U11':item.update(x=15,y=66)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Moved U11 back-side comparator; release signal copper:',len(removed))
