"""Release the old reference copper so the bias resistor can exit normally."""
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
tracks=list(b.GetTracks());removed=[]
for t in tracks:
    if t.GetNetname()=='UPS_REF_1V24':removed.append(t);b.Remove(t)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
print('Released low-current reference copper:',len(removed))
