from pathlib import Path
import sys,pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
b=p.LoadBoard(str(file))
assert p.ImportSpecctraSES(b,str(Path(sys.argv[1]).resolve()))
p.SaveBoard(str(file),b)
print('Imported V5 session:',len(b.GetTracks()),'tracks/vias; native DRC required')
