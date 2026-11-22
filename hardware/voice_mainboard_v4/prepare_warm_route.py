"""Release incomplete exploratory tails; reroute signals around ground pours.

Removals are recorded, and native unconnected items remain the acceptance
criterion. No required pad/net is removed and no clearance rule is weakened.
"""
from pathlib import Path
import json,shutil
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
shutil.copy2(file,'build/voice-v4-before-warm.kicad_pcb')
b=p.LoadBoard(str(file));d=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
bad={q['uuid']for v in d['violations'] if v['type']in ['track_dangling','via_dangling'] for q in v['items']}
removed=[]
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString()in bad or (t.GetNetname()=='GND' and not isinstance(t,p.PCB_VIA)):
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'reason':'dangling exploratory tail'if t.m_Uuid.AsString()in bad else'ground trace replaced by poured ground reference'})
        b.Remove(t)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
dest=Path('build/voice-v4-warm.dsn');assert p.ExportSpecctraDSN(b,str(dest))
s=dest.read_text(encoding='utf8').replace('(clearance 50 (type smd_smd))','(clearance 150 (type smd_smd))')
dest.write_text(s,encoding='utf8')
(ROOT/'exports/warm-route-preparation.json').write_text(json.dumps({'removed':removed,'acceptance':'native DRC and zero unconnected required','manufacturing_ready':False},indent=2)+'\n',encoding='utf8')
print('Warm routing export;',len(removed),'logged tails/ground traces replaced')
