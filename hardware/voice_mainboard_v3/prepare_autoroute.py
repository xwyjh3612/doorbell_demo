"""Export the frozen reviewed copper; autoroute only outstanding connections.

Inner layers remain power/reference layers. Existing RF/USB and converter
routes are protected in DSN; verify their copper again after session import.
"""
from pathlib import Path
import pcbnew as p,json,re
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
initial=list(b.GetTracks())
# Remove unused obsolete open tails after V2 header moves. Never remove
# electrical violations to make a report look clean.
d=json.loads((root/'exports/power-route-drc.json').read_text(encoding='utf8'))
bad={i['uuid'] for v in d['violations'] if v['type'] in ['track_dangling','via_dangling'] for i in v['items']}
for t in initial:
    if t.m_Uuid.AsString() in bad:b.Remove(t)
for t in b.GetTracks():t.SetLocked(True)
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
dest=Path('build/voice-v3-route.dsn')
assert p.ExportSpecctraDSN(b,str(dest))
s=dest.read_text(encoding='utf8')
for name in ['In1.Cu','In2.Cu']:
    s=s.replace('(layer '+name+'\n      (type signal)', '(layer '+name+'\n      (type power)')
# KiCad exports pad-specific 0.05mm smd_smd spacing; use 0.15mm matching
# the DGK package minimum, retaining 0.2mm for tracks and other geometry.
s=s.replace('(clearance 50 (type smd_smd))','(clearance 150 (type smd_smd))')
dest.write_text(s,encoding='utf8')
print('DSN exported, copper locked:',len(list(b.GetTracks())),'items; old dangling tails removed:',len(bad))
