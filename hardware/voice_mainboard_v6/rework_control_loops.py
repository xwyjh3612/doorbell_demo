"""Move program/current-setting resistors next to their actual analog pins."""
from pathlib import Path
import json,pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v6.kicad_pcb';b=p.LoadBoard(str(file));held=[]
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'));parts={q['ref']:q for q in d['parts']}
for f in b.GetFootprints():
    if f.GetReference() in ['R63','R64']:
        x,y={'R63':(38.4,64.3),'R64':(37.3,55)}[f.GetReference()]
        f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));parts[f.GetReference()].update(x=x,y=y)
for t in list(b.GetTracks()):
    if t.GetNetname() in ['UPS_ISET','CHG_PROG']:held.append(t);b.Remove(t)
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
p.SaveBoard(str(file),b)
for t in held:t.thisown=False
