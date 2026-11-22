"""Probe ordinary 0.3mm drilling without silently lowering clearances.

The probe is a separate board. Adopt it only after its independent DRC passes;
RF/USB route coordinates and widths are not changed.
"""
from pathlib import Path
import json
import pcbnew as p
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
report=[]
for v in b.GetTracks():
    if isinstance(v,p.PCB_VIA) and v.GetDrill()<p.FromMM(.3):
        report.append({'uuid':v.m_Uuid.AsString(),'net':v.GetNetname(),
                       'xy_mm':[p.ToMM(v.GetPosition().x),p.ToMM(v.GetPosition().y)]})
        v.SetDrill(p.FromMM(.3));v.SetWidth(p.FromMM(.55))
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(root/'exports/via-probe.kicad_pcb'),b)
(root/'exports/via-standardization.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Probe only:',len(report),'vias enlarged to 0.55/0.3mm')
