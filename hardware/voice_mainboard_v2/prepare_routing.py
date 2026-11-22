"""Export router input with internal layers reserved for continuous ground.

Autorouting output is engineering input: it must pass KiCad DRC and review.
No Gerber release is performed by this script.
"""
from pathlib import Path
import pcbnew as pcb
import re

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
board=pcb.LoadBoard(str(ROOT/'voice_mainboard_v2.kicad_pcb'))
for t in board.GetTracks():t.SetLocked(True)
pcb.SaveBoard(str(ROOT/'voice_mainboard_v2.kicad_pcb'),board)
dsn=WORK/'build/voice-v2-route.dsn'
assert pcb.ExportSpecctraDSN(board,str(dsn))
text=dsn.read_text(encoding='utf-8')
for layer in ['In1.Cu','In2.Cu']:
    text=text.replace(f'(layer {layer}\n      (type signal)',f'(layer {layer}\n      (type power)',1)
# Reserved inner layers still exist for via spans; no signal routes are allowed.
# Empty-net mechanical pads retain their KiCad geometry in the export.
dsn.write_text(text,encoding='utf-8')
print('Router input exported:',dsn)
