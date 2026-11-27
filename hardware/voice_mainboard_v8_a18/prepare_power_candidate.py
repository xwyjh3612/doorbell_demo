"""Independent two-layer placement with the modem buck close to its supply.

Never overwrite the current work PCB. A failed candidate is kept as evidence.
"""
from pathlib import Path
import json, shutil
import pcbnew as p
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'candidate_power_2layer';OUT.mkdir(exist_ok=True)
NAME='voice_mainboard_a18_power_2layer'
for ext in ['kicad_sch','kicad_pro','kicad_dru']:
    shutil.copy2(ROOT/('voice_mainboard_v8_a18.'+ext),OUT/(NAME+'.'+ext))
for table in ['fp-lib-table','sym-lib-table']:
    (OUT/table).write_text((ROOT/table).read_text(encoding='utf-8').replace('${KIPRJMOD}/','${KIPRJMOD}/../'),encoding='utf-8')
b=p.LoadBoard(str(ROOT/'voice_mainboard_v8_a18.kicad_pcb'));held=[]
for t in list(b.GetTracks()):held.append(t);b.Remove(t)
for z in list(b.Zones()):
    if not z.GetIsRuleArea():held.append(z);b.Remove(z)
design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
parts={q['ref']:q for q in design['parts']};fps={f.GetReference():f for f in b.GetFootprints()}
# Back-side modem supply: shortened high-current output and local switching
# loop. Upper enclosure notch and assembly heights still need physical fit.
moves={
    'U2':(55.5,8.5,180), 'L1':(54.5,13.8,270),
    'C4':(60,8,0), 'C6':(60.5,12.5,0), 'C7':(60.5,16.3,0),
    'R2':(60,5,90), 'R3':(63,5,90), 'C37':(64,9.5,0),
}
for ref,(x,y,angle)in moves.items():
    f=fps[ref];f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
    if f.GetLayer()!=p.B_Cu:f.Flip(f.GetPosition(),False)
    f.SetOrientationDegrees(angle)
    parts[ref].update(x=x,y=y,angle=angle,side='B')
    parts[ref]['note']=parts[ref].get('note','')+' A18 power candidate: modem buck relocated to back near module supply pads; not released.'
design.update(revision='A18 TWO-LAYER LOCAL MODEM POWER CANDIDATE',manufacturing_ready=False,status='PLACEMENT CHECK REQUIRED; NOT RELEASED')
b.BuildConnectivity();p.SaveBoard(str(OUT/(NAME+'.kicad_pcb')),b)
(OUT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
print('Independent two-layer power candidate created; modem converter moved near module supply.')
for t in held:t.thisown=False
