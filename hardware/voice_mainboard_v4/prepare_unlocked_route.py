"""Release signal detours for rip-up routing while preserving wide power traces.

Use standard drilling and retain a board snapshot. Automatic routing is followed
by native DRC and by a separate power/RF/USB engineering review.
"""
from pathlib import Path
import json,shutil
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
shutil.copy2(file,'build/voice-v4-before-unlocked.kicad_pcb')
b=p.LoadBoard(str(file));old=p.LoadBoard('build/voice-v4-before-local-rework.kicad_pcb');held=[]
d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
for f in b.GetFootprints():
    if f.GetReference()in ['R61','R62']:
        orig=next(q for q in old.GetFootprints()if q.GetReference()==f.GetReference())
        f.SetPosition(orig.GetPosition());f.SetOrientation(orig.GetOrientation())
        for part in d['parts']:
            if part['ref']==f.GetReference():part.update(x=p.ToMM(f.GetPosition().x),y=p.ToMM(f.GetPosition().y),angle=f.GetOrientationDegrees())
for t in list(b.GetTracks()):
    if t.GetNetname()in ['AMP_GAIN','AMP_SD','UPS_SW','GND']:
        b.Remove(t);held.append(t)
    else:t.SetLocked(False)
for t in old.GetTracks():
    if t.GetNetname()!='UPS_SW':continue
    if isinstance(t,p.PCB_VIA):
        q=p.PCB_VIA(b);q.SetPosition(t.GetPosition());q.SetWidth(t.GetWidth(p.F_Cu));q.SetDrill(t.GetDrill());q.SetViaType(p.VIATYPE_THROUGH);q.SetLayerPair(p.F_Cu,p.B_Cu)
    else:
        q=p.PCB_TRACK(b);q.SetStart(t.GetStart());q.SetEnd(t.GetEnd());q.SetWidth(t.GetWidth());q.SetLayer(t.GetLayer())
    q.SetNetCode(b.FindNet('UPS_SW').GetNetCode());q.SetLocked(True);b.Add(q);held.append(q)
for t in b.GetTracks():
    if not isinstance(t,p.PCB_VIA)and p.ToMM(t.GetWidth())>=.45:t.SetLocked(True)
p.SaveBoard(str(file),b)
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Released signal routes; refill and export in a fresh native process, then run DRC.')
