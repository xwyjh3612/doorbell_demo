"""Move local decoupling/series parts closer to their pins, releasing their nets."""
from pathlib import Path
import json
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
b=p.LoadBoard(str(file))
data=json.loads((ROOT/'design.json').read_text(encoding='utf8'))
prices=json.loads((ROOT/'cost/part-price-inputs.json').read_text(encoding='utf8'))
fps={f.GetReference():f for f in b.GetFootprints()}
if 'U_UPS' in fps:
    fp=fps.pop('U_UPS');fp.SetReference('U15');fps['U15']=fp
    for q in data['parts']:
        if q['ref']=='U_UPS':q['ref']='U15'
    prices['U15']=prices.pop('U_UPS')
positions={'C57':(7,11,0),'C58':(7,8,0),'C56':(8,13.5,0),'R57':(9.25,16,0),
    'R10':(55,34.5,180),'R11':(55,31.5,180)}
for ref,(x,y,a) in positions.items():
    fp=fps[ref];fp.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));fp.SetOrientationDegrees(a)
    for q in data['parts']:
        if q['ref']==ref:q.update(x=x,y=y,angle=a)
clear={'ESP_3V3','ESP_EN','M_SIM_CLK','SIM_CLK','M_SIM_RESET','SIM_RESET','SIM_VCC','GND'}
held=[]
for t in list(b.GetTracks()):
    if t.GetNetname() in clear:held.append(t);b.Remove(t)
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(file),b)
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'cost/part-price-inputs.json').write_text(json.dumps(prices,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for t in held:t.thisown=False
print('Moved local bypass/series parts; released',len(held),'tracks/vias; renamed UPS contract U15 for legal annotation')
