"""Export only this two-layer candidate; preserve pre-routed local power loops."""
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
b=p.LoadBoard(str(ROOT/'voice_mainboard_v4.kicad_pcb'))
assert b.GetCopperLayerCount()==2
dest=Path('build/voice-v4-route.dsn')
assert p.ExportSpecctraDSN(b,str(dest))
s=dest.read_text(encoding='utf8')
s=s.replace('(clearance 50 (type smd_smd))','(clearance 150 (type smd_smd))')
dest.write_text(s,encoding='utf8')
print('Exported V4 DSN,',len(list(b.GetTracks())),'locked pre-route items')
