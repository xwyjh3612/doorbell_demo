"""Package only saved final CAD/reports, never failed routing probes/logs."""
from pathlib import Path
import json,hashlib,zipfile
root=Path(__file__).resolve().parent;repo=root.parent.parent
names=['README.md','.gitattributes','.gitignore','工程复核及首板验收.md','voice_mainboard_v3.kicad_pro',
 'voice_mainboard_v3.kicad_pcb','voice_mainboard_v3.kicad_sch','voice_mainboard_v3.kicad_dru',
 'VoiceV2.kicad_sym','fp-lib-table','sym-lib-table','design.json','schematic-ids.json',
 'generate_schematic.py','verify_design.py','simulate_ups_controls.py','audit_power.py',
 'build_bom.py','build_cost.py','derive_processing_budget.py','fix_assembly_attributes.py','build_review.py','serve_review.py','package_review.py',
 'exports/front.svg','exports/back.svg','exports/schematic/voice_mainboard_v3.svg',
 'exports/validation.json','exports/current-drc.json','exports/erc.json',
 'exports/voice_mainboard_v3.net.xml','exports/power-audit.json','exports/review.html']
files=[root/n for n in names]
for folder in ['VoiceV2.pretty','exports/ups-simulation','exports/fabrication-unreleased','cost']:
    files.extend(p for p in(root/folder).rglob('*')if p.is_file()and p.suffix not in ['.pyc','.bak'])
files.extend([repo/'.gitattributes',repo/'hardware/voice_mainboard_v2/generate_schematic.py',
 repo/'outputs/voice-v3-20261122/语音对讲V3主板费用.xlsx',
 repo/'tests/at_recovery_batch_20261121.md',repo/'tests/at_recovery_40_final.json',
 repo/'tests/at_recovery_32_hangup_panic.txt'])
assert len(files)==len(set(files))
for file in files:assert file.is_file(),str(file)
for file in files:
    if file.suffix in ['.xlsx','.zip','.png']:continue
    data=file.read_bytes()
    if b'\r\n'in data:
        data.decode('utf8');file.write_bytes(data.replace(b'\r\n',b'\n'))
bom=json.loads((root/'cost/bom-and-process.json').read_text(encoding='utf8'))
assert bom['source_pcb_sha256']==hashlib.sha256((root/'voice_mainboard_v3.kicad_pcb').read_bytes()).hexdigest(),'Refresh BOM/cost after final saved/normalized PCB'
records=[{'path':p.relative_to(repo).as_posix(),'bytes':p.stat().st_size,
 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in sorted(files)]
manifest={'revision':'V3-INTEGRATED-UPS-20261122','manufacturing_released':False,
 'description':'Saved native engineering design, unreleased fabrication/DFM files, source-priced BOM and final old-device call-test summary',
 'files':records}
mf=root/'exports/package-manifest.json';mf.write_bytes((json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
files.append(mf)
out=root/'exports/voice-v3-engineering-review.zip'
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
    for p in sorted(files):z.write(p,p.relative_to(repo).as_posix())
with zipfile.ZipFile(out)as z:assert z.testzip()is None
print(json.dumps({'package':str(out),'files':len(files),'bytes':out.stat().st_size,'manufacturing_released':False}))
