"""Inventory real installed model files for the exact current two-layer board."""
from pathlib import Path
import hashlib,json,os,re
import pcbnew as p

ROOT=Path(__file__).resolve().parent
FILE=Path(os.environ['A18_AUDIT_BOARD']).resolve()
repo=ROOT.parents[1]
variables={'KIPRJMOD':str(FILE.parent),'KICAD9_3DMODEL_DIR':str(repo/'build/cad-tools/kicad/share/kicad/3dmodels')}
b=p.LoadBoard(str(FILE));inventory=[]
for f in b.GetFootprints():
    models=[]
    for m in f.Models():
        source=m.m_Filename
        resolved=re.sub(r'\$\{([^}]+)\}',lambda q:variables.get(q[1],os.environ.get(q[1],q[0])),source)
        models.append({'source':source,'file_exists':Path(resolved).is_file(),'show':m.m_Show})
    inventory.append({'ref':f.GetReference(),'DNP':f.IsDNP(),'models':models})
missing=[q['ref'] for q in inventory if not any(m['file_exists'] and m['show'] for m in q['models'])]
report={'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'count':len(inventory),
        'with_existing_model':len(inventory)-len(missing),'without_existing_model':missing,
        'inventory':inventory,'assembled_collision_verification_complete':False}
(FILE.parent/'exports/model-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Model files found:',report['with_existing_model'],'; missing:',len(missing))
