"""Use the actual Omron B3F-1000 6.5x4.5mm lead pattern, 4.3mm height."""
from pathlib import Path
import json
import pcbnew as p
root=Path(__file__).resolve().parent
library=str(Path('build/cad-tools/kicad/share/kicad/footprints/Button_Switch_THT.pretty').resolve())
loaded=[p.FootprintLoad(library,'SW_PUSH_6mm_H4.3mm')for _ in range(2)]
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'));d=json.loads((root/'design.json').read_text(encoding='utf8'))
held=[]
for ref,new in zip(['SW1','SW2'],loaded):
    old=next(f for f in b.GetFootprints()if f.GetReference()==ref)
    nets={pd.GetNumber():pd.GetNetname()for pd in old.Pads()}
    # The four physical through-hole legs are unchanged (two electrical nodes).
    old_geometry=sorted((pd.GetNumber(),p.ToMM(pd.GetPosition().x-old.GetPosition().x),p.ToMM(pd.GetPosition().y-old.GetPosition().y))for pd in old.Pads())
    new.SetPosition(old.GetPosition());new.SetOrientation(old.GetOrientation())
    new_geometry=sorted((pd.GetNumber(),p.ToMM(pd.GetPosition().x-new.GetPosition().x),p.ToMM(pd.GetPosition().y-new.GetPosition().y))for pd in new.Pads())
    assert old_geometry==new_geometry,'Switch leg pattern differs'
    new.SetReference(ref);new.SetValue(old.GetValue());new.SetPath(old.GetPath())
    new.Reference().SetLayer(p.F_Fab);new.Value().SetVisible(False)
    new.SetFPID(p.LIB_ID('Button_Switch_THT','SW_PUSH_6mm_H4.3mm'))
    for pd in new.Pads():pd.SetNet(b.FindNet(nets[pd.GetNumber()]))
    held.append(old);b.Remove(old);b.Add(new)
    item=next(x for x in d['parts']if x['ref']==ref)
    item.update(mpn='B3F-1000',lcsc='C93157',footprint='Button_Switch_THT:SW_PUSH_6mm_H4.3mm',
      source='https://item.szlcsc.com/94352.html',procurement_status='selected_catalog_part_land_review_required',
      note='Omron B3F-1000: silver contact, body6x6mm, height4.3mm; four leads on6.5x4.5mm. Manufacturer B3F catalog page dimensions checked; stock688 at20261122,0.6904CNY public. Actual button/firmware behavior still needs prototype validation.')
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Both switches share B3F-1000 MPN; four legs retained; 4.3mm model corrected')
