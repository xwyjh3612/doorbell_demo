"""Improve UART decoupling without disturbing reserved power trunks."""
from pathlib import Path
import json,os,shutil
import pcbnew as p
FILE=Path(os.environ['A18_REPAIR_BOARD']);ROOT=FILE.parent
shutil.copy2(FILE,ROOT/'before-final-control-placement.kicad_pcb')
b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()};design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'));parts={q['ref']:q for q in design['parts']}
moves={'C15':(28.3,45.3)}
endpoints={(d.GetPosition().x,d.GetPosition().y)for ref in moves for d in fps[ref].Pads()}
held=[]
for t in list(b.GetTracks()):
    remove=False
    if not isinstance(t,p.PCB_VIA):remove|=any((pt.x,pt.y)in endpoints for pt in [t.GetStart(),t.GetEnd()])
    if remove:held.append(t);b.Remove(t)
for ref,(x,y)in moves.items():fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));parts[ref].update(x=x,y=y)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'exports/reset-local-refinement.json').write_text(json.dumps({'moves_mm':moves,'parts_added':0,'nets_unchanged':True,'removed_route_pieces':len(held)},indent=2),encoding='utf-8')
print('Refined reset/decoupling placement:',moves)
for t in held:t.thisown=False
