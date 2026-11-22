"""Align native assembly flags with actual plated/SMT pad technology."""
from pathlib import Path
import json,re
import pcbnew as p
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
for fp in b.GetFootprints():
    ref=fp.GetReference()
    if ref.startswith(('H','TP')):continue
    pads=list(fp.Pads())
    technology=p.FP_THROUGH_HOLE if any(pd.GetAttribute()==p.PAD_ATTRIB_PTH for pd in pads)else p.FP_SMD
    attr=fp.GetAttributes()
    fp.SetAttributes((attr&~(p.FP_THROUGH_HOLE|p.FP_SMD))|technology)
p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
design=json.loads((root/'design.json').read_text(encoding='utf8'))
for part in design['parts']:
    if part['ref']not in ['U1','U9','U10','J2']:continue
    name=part['footprint'].split(':')[-1]
    path=root/'VoiceV2.pretty'/(name+'.kicad_mod')
    text=path.read_text(encoding='utf8');attr='through_hole'if part['ref']=='J2'else 'smd'
    if re.search(r'\(attr [^)]*\)',text):text=re.sub(r'\(attr [^)]*\)','(attr '+attr+')',text,count=1)
    else:text=text[:text.rfind(')')]+'\t(attr '+attr+')\n'+text[text.rfind(')'):]
    path.write_text(text,encoding='utf8')
print('Native assembly flags aligned to actual pads; J2 THT, U1/U9/U10 SMD; no net or copper changes')
