"""One-time migration of the saved V6 prototype; keep its already-routed copper."""
from pathlib import Path
import copy,json,collections
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v6.kicad_pcb'
b=p.LoadBoard(str(file));d=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
parts={q['ref']:q for q in d['parts']}
base={q['ref']:q for q in json.loads((ROOT.parent/'voice_mainboard_v5/design.json').read_text(encoding='utf8'))['parts']}
pricefile=ROOT/'cost/part-price-inputs.json';prices=json.loads(pricefile.read_text(encoding='utf8'))
baseprice=json.loads((ROOT.parent/'voice_mainboard_v5/cost/part-price-inputs.json').read_text(encoding='utf8'))
for old,new in [('L4','L5'),('R61','R75'),('R62','R76'),('TP12','TP15'),('TP13','TP16'),('TP14','TP17')]:
    if new in parts:continue
    q=copy.deepcopy(base[old]);q['ref']=new
    candidates=[f for f in b.GetFootprints() if f.GetReference()==old and all(pad.GetNetname()==q['pins'].get(pad.GetNumber(),'') for pad in f.Pads())]
    assert len(candidates)==1,(old,len(candidates))
    f=candidates[0];f.SetReference(new);parts[new]=q
    if old in baseprice:prices[new]=baseprice[old]
parts['U18']['names']['7']=['VOUT_COMMON','passive']
assert len(list(b.GetFootprints()))==len(parts)
assert all(n==1 for n in collections.Counter(f.GetReference() for f in b.GetFootprints()).values())
d['parts']=list(parts.values());(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
pricefile.write_text(json.dumps(prices,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
p.SaveBoard(str(file),b)
print('Restored original ESP inductor, amplifier straps, modem debug and 1.8V test pads; unique references',len(parts))
