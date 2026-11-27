"""Try explicit small positions, retaining only a native-clean isolated trial.

No tracks or pad nets are removed. Existing copper contacts must survive or be
restored separately, and acceptance into the main board remains independent.
"""
import json
import os
from pathlib import Path
import subprocess
import pcbnew as p

root=Path(__file__).resolve().parents[2]
file=Path(os.environ['A18_REPAIR_BOARD']).resolve()
original=file.read_bytes()
ref=os.environ['A18_SHIFT_REF']
manager=p.GetSettingsManager();manager.LoadProject(str(file.with_suffix('.kicad_pro')))
records=[]
for x,y,angle,side in json.loads(os.environ['A18_SHIFT_POSITIONS']):
    file.write_bytes(original)
    b=p.LoadBoard(str(file));b.SetProject(manager.GetProject(str(file.with_suffix('.kicad_pro'))));b.SynchronizeNetsAndNetClasses(False)
    f=next(f for f in b.GetFootprints()if f.GetReference()==ref)
    layer=p.F_Cu if side=='F'else p.B_Cu
    if f.GetLayer()!=layer:f.Flip(f.GetPosition(),False)
    f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));f.SetOrientationDegrees(angle)
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
    resultfile=file.parent/'exports'/('shift-'+ref+'-native.json')
    subprocess.run([str(root/'build/cad-tools/kicad/bin/kicad-cli.exe'),'pcb','drc','--format','json','--output',str(resultfile),str(file)],check=True,capture_output=True)
    r=json.loads(resultfile.read_text(encoding='utf-8'))
    record={'ref':ref,'x':x,'y':y,'angle':angle,'side':side,'unconnected':len(r['unconnected_items']),'findings':r['violations']}
    records.append(record)
    print(json.dumps({k:v for k,v in record.items()if k!='findings'}),flush=True)
    hard=[v for v in r['violations']if v['type']not in('track_dangling','via_dangling')]
    if not hard:
        designfile=file.parent/'design.json'
        design=json.loads(designfile.read_text(encoding='utf-8'))
        for q in design['parts']:
            if q['ref']==ref:q.update(x=x,y=y,angle=angle,side=side)
        designfile.write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
        break
else:file.write_bytes(original)
(file.parent/'exports'/('shift-'+ref+'-trials.json')).write_text(json.dumps(records,indent=2),encoding='utf-8')
