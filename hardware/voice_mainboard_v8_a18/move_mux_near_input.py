"""Move the supply selector out of the dense modem/UART escape region."""
from pathlib import Path
import os,json
import pcbnew as p
FILE=Path(os.environ['A18_REPAIR_BOARD']);ROOT=FILE.parent
b=p.LoadBoard(str(FILE));design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'));parts={q['ref']:q for q in design['parts']};fps={f.GetReference():f for f in b.GetFootprints()}
moves={'U18':(66,40),'R70':(62,35.5),'R71':(66,36.5),'C71':(69.5,38),'C72':(68.5,43)}
nets={d.GetNetname()for ref in moves for d in fps[ref].Pads()if d.GetNetname()!='GND'}
held=[]
for t in list(b.GetTracks()):
    if t.GetNetname()in nets:held.append(t);b.Remove(t)
for ref,(x,y)in moves.items():
    f=fps[ref];f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));parts[ref].update(x=x,y=y)
    if ref in ['R71','C72']:
        f.SetOrientationDegrees(0);parts[ref]['angle']=0
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'exports/mux-placement-refinement.json').write_text(json.dumps({'moves_mm':moves,'removed_net_routes':sorted(nets),'placement_DRC_required':True},indent=2),encoding='utf-8')
print('Moved supply selector near DC input:',moves)
for t in held:t.thisown=False
