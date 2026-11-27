"""Finalize the reviewed package without changing the PCB or release status."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
OUT = ROOT/'prototype_review_20261127'
BOARD = ROOT/'power_relayout_candidate/voice_mainboard_a18_2layer.kicad_pcb'

def sha(f):
    return hashlib.sha256(f.read_bytes()).hexdigest()

status = json.loads((OUT/'release-status.json').read_text(encoding='utf-8'))
assert status['PCB_sha256'] == sha(BOARD) == sha(OUT/'source'/BOARD.name)
assert status['manufacturing_ready'] is False
assert status['native_checks'] == {'violations':0,'schematic_parity':0,'unconnected_items':0}
xlsx = REPO/'outputs/voice-mainboard-review-20261127/voice-mainboard-bom.xlsx'
assert xlsx.is_file()
with zipfile.ZipFile(xlsx) as archive:
    assert archive.testzip() is None
    assert 'xl/workbook.xml' in archive.namelist()
shutil.copy2(xlsx, OUT/'assembly/voice-mainboard-bom.xlsx')
shutil.copy2(ROOT/'设计完成度与交付.md', OUT/'设计完成度与交付.md')
readme = OUT/'README.md'
text = readme.read_text(encoding='utf-8')
text = text.replace('`assembly`是物料和原生KiCad坐标', '`assembly`是Excel/CSV物料表和原生KiCad坐标')
readme.write_text(text, encoding='utf-8')
layers = {f.suffix for f in (OUT/'fabrication').iterdir() if f.suffix in ('.gtl','.gbl','.g1','.g2','.g3','.g4')}
assert layers == {'.gtl','.gbl'}, layers
manifest = {str(f.relative_to(OUT)).replace('\\','/'):sha(f) for f in sorted(OUT.rglob('*'))
            if f.is_file() and f.name != 'manifest.json'}
(OUT/'manifest.json').write_text(json.dumps({'PCB_sha256':sha(BOARD),'files':manifest},indent=2),encoding='utf-8')
zip_path = OUT.with_suffix('.zip')
temp = OUT.with_suffix('.zip.part')
assert zip_path.resolve().is_relative_to(ROOT) and temp.resolve().is_relative_to(ROOT)
with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
    for f in sorted(OUT.rglob('*')):
        if f.is_file():
            archive.write(f,str(f.relative_to(OUT.parent)))
with zipfile.ZipFile(temp) as archive:
    assert archive.testzip() is None
    for relative,digest in manifest.items():
        data=archive.read(OUT.name+'/'+relative)
        assert hashlib.sha256(data).hexdigest()==digest,relative
temp.replace(zip_path)
print(json.dumps({'zip':str(zip_path),'size_bytes':zip_path.stat().st_size,'files_verified':len(manifest),
                  'PCB_sha256':sha(BOARD),'copper_layers':2,'manufacturing_ready':False},indent=2))
