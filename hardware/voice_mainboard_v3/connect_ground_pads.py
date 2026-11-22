"""Connect populated ground pads to checked conventional through-vias."""
from pathlib import Path
import sys,json
import pcbnew as p
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
b=r.board;report=[]
pads=[(fp.GetReference(),pd.GetNumber())for fp in b.GetFootprints()for pd in fp.Pads()if pd.GetNetname()=='GND'and pd.GetAttribute()==p.PAD_ATTRIB_SMD]
try:
    for index,pair in enumerate(pads):
        try:r.escapevia('ground_pad_'+str(index),pair,neck=.2)
        except RuntimeError as e:report.append({'pad':pair,'connected':False,'reason':str(e)});print('GROUND ESCAPE FAILED',pair,str(e),flush=True);continue
        report.append({'pad':pair,'connected':True,'via':r.pos(r.virtual['ground_pad_'+str(index)])})
finally:
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    (root/'exports/ground-pad-connections.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
