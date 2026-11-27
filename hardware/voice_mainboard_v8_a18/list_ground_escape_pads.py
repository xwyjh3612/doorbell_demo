"""List ordinary ground pads; exposed die pads require separate thermal review."""
import os
import pcbnew as p
b=p.LoadBoard(os.environ['A18_REPAIR_BOARD']);targets=[]
for f in b.GetFootprints():
    for d in f.Pads():
        if d.GetNetname()!='GND' or d.GetAttribute()!=p.PAD_ATTRIB_SMD:continue
        if f.GetReference()=='U7'and d.GetNumber()=='41':continue
        if p.ToMM(d.GetSize().x)*p.ToMM(d.GetSize().y)>3:continue
        if f.GetReference()=='U1' and d.GetNumber().isdigit() and int(d.GetNumber())>48:continue
        value=f.GetReference()+'.'+d.GetNumber()
        if value not in targets:targets.append(value)
print(','.join(targets))
