"""Export partial routing to DSN after removing only native-reported tails."""
from pathlib import Path
import json,pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
b=p.LoadBoard(str(file))
report=ROOT/'exports/routed-drc.json'
if not report.exists():report=ROOT/'exports/pre-route-drc.json'
d=json.loads(report.read_text(encoding='utf8'))
bad={q['uuid'] for v in d['violations'] if v['type'] in ['track_dangling','via_dangling'] for q in v['items']}
held=[]
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString() in bad:
        held.append(t);b.Remove(t)
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(file),b)
dest=Path('build/voice-v5-route.dsn')
assert p.ExportSpecctraDSN(b,str(dest))
s=dest.read_text(encoding='utf8').replace('(clearance 50 (type smd_smd))','(clearance 200 (type smd_smd))')
dest.write_text(s,encoding='utf8')
for item in held:item.thisown=False
print('Exported V5 DSN;',len(held),'reported tails removed')
