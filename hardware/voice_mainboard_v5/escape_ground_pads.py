"""Connect isolated required ground pads to back copper using ordinary vias."""
from pathlib import Path
import json
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
r,m=load();b=r.board;file=ROOT/'voice_mainboard_v5.kicad_pcb'
refs={('U1','27'),('U1','34'),('C4','2'),('C7','2'),('R3','2'),('U1','95'),('J11','2'),('U1','36'),('U1','37'),('R60','2'),('C10','2')}
report=[]
for f in b.GetFootprints():
    for pd in f.Pads():
        if (f.GetReference(),pd.GetNumber()) not in refs:continue
        name='REQUIRED_GND_'+str(len(report));r.virtual[name]=pd
        try:
            r.escapevia(name+'_via',(name,0),neck=.2)
            report.append({'ref':f.GetReference(),'pin':pd.GetNumber(),'via':r.pos(r.virtual[name+'_via']),'escape':True})
        except RuntimeError as e:
            report.append({'ref':f.GetReference(),'pin':pd.GetNumber(),'escape':False,'reason':str(e)})
        p.SaveBoard(str(file),b)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
(ROOT/'exports/required-ground-vias.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
