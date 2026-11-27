"""Use a standard larger zero-ohm selector land in an isolated USB trial.

The two electrical nets, resistor value and mutually exclusive population
policy are unchanged. The larger physical body can span a narrow routing
barrier. Native placement, routing, ERC and final independent acceptance are
still required; this script cannot release a board.
"""
import json
import os
import re
import shutil
import datetime
from pathlib import Path
from comparison_route_geometry import b,FILE,p

ref=os.environ.get('A18_SELECTOR_REF','R28')
name=os.environ.get('A18_SELECTOR_LAND','R_0805_2012Metric')
assert ref in ('R28','R29') and name in ('R_0603_1608Metric','R_0805_2012Metric','R_1206_3216Metric')
old=next(f for f in b.GetFootprints()if f.GetReference()==ref)
assert old.GetValue().startswith('0R USB HOST') and old.IsDNP()
oldid=str(old.GetFPID().GetLibNickname())+':'+str(old.GetFPID().GetLibItemName())
newid='Resistor_SMD:'+name
snapshot=FILE.parent/'iterations'/('selector-land-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
for file in [FILE,FILE.with_suffix('.kicad_sch'),FILE.parent/'design.json']:
    shutil.copy2(file,snapshot/file.name)
repo=Path(__file__).resolve().parents[2]
new=p.FootprintLoad(str(repo/'build/cad-tools/kicad/share/kicad/footprints/Resistor_SMD.pretty'),name)
assert new
new.SetFPID(p.LIB_ID('Resistor_SMD',name))
if old.GetLayer()==p.B_Cu:new.Flip(new.GetPosition(),False)
new.SetPosition(old.GetPosition());new.SetOrientationDegrees(old.GetOrientationDegrees())
new.SetReference(ref);new.SetValue(old.GetValue());new.SetPath(old.GetPath());new.SetDNP(True)
contract={d.GetNumber():d.GetNetname()for d in old.Pads()}
assert set(contract)=={'1','2'}
for d in new.Pads():d.SetNet(b.FindNet(contract[d.GetNumber()]))
for field,newfield in [(old.Reference(),new.Reference()),(old.Value(),new.Value())]:
    newfield.SetLayer(field.GetLayer());newfield.SetPosition(field.GetPosition());newfield.SetVisible(field.IsVisible())
    newfield.SetTextSize(field.GetTextSize());newfield.SetTextThickness(field.GetTextThickness())
b.Remove(old);b.Add(new)
sch=FILE.with_suffix('.kicad_sch');text=sch.read_text(encoding='utf-8')
mark=text.rindex('(property "Reference" "'+ref+'"')
stack=[];quoted=False;escape=False
for i,ch in enumerate(text[:mark]):
    if quoted:
        if escape:escape=False
        elif ch=='\\':escape=True
        elif ch=='"':quoted=False
    elif ch=='"':quoted=True
    elif ch=='(':stack.append(i)
    elif ch==')':stack.pop()
start=next(i for i in reversed(stack)if text.startswith('(symbol',i))
depth=0;quoted=False;escape=False;end=None
for i in range(start,len(text)):
    ch=text[i]
    if quoted:
        if escape:escape=False
        elif ch=='\\':escape=True
        elif ch=='"':quoted=False
    elif ch=='"':quoted=True
    elif ch=='(':depth+=1
    elif ch==')':
        depth-=1
        if depth==0:end=i+1;break
assert end
block=text[start:end]
assert '(property "Footprint" "'+oldid+'"'in block
block,n=re.subn(r'(\(property "Footprint" ")[^"]*(")',lambda m:m[1]+newid+m[2],block,count=1)
assert n==1
sch.write_text(text[:start]+block+text[end:],encoding='utf-8')
designfile=FILE.parent/'design.json';design=json.loads(designfile.read_text(encoding='utf-8'))
q=next(q for q in design['parts']if q['ref']==ref)
q['footprint']=newid
size={'R_0603_1608Metric':'0603','R_0805_2012Metric':'0805','R_1206_3216Metric':'1206'}[name]
q.update(mpn='RC'+size+'JR070RL',lcsc=None,source='',price_basis='standard zero-ohm selector; exact procurement SKU pending')
q['note']=q.get('note','')+' Larger standard '+size+' land spans local copper barrier; USB service/host population remains mutually exclusive.'
designfile.write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
old.thisown=False
report={'reference':ref,'old_footprint':oldid,'new_footprint':newid,'pin_contract':contract,'DNP_retained':True,'snapshot':str(snapshot),'manufacturing_ready':False}
(FILE.parent/'exports/selector-land-change.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
