from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
for f in sorted(b.GetFootprints(),key=lambda f:f.GetReference()):
    if f.GetReference() in ['U8','U9','U10','U11','U12','L3','J2','JP4'] or (f.GetReference().startswith('C') and f.GetReference()[1:].isdigit() and int(f.GetReference()[1:])>=38):
        print(f.GetReference(),[(pd.GetNumber(),pd.GetNetname(),round(p.ToMM(pd.GetPosition().x),4),round(p.ToMM(pd.GetPosition().y),4),round(p.ToMM(pd.GetSize().x),3),round(p.ToMM(pd.GetSize().y),3)) for pd in f.Pads()])
