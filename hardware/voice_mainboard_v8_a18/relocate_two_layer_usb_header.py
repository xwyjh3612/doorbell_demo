"""Keep the USB reserve beside ESP USB pins, clear of rear charger pads.

Same connector, resistors, DNP choices and nets. Selected placement was
checked against full courtyards and rear copper; native DRC remains required.
"""
from pathlib import Path
import datetime,json,shutil
import pcbnew as p
OUT=Path(__file__).resolve().parent/'two_layer_work';FILE=OUT/'voice_mainboard_a18_2layer.kicad_pcb'
snap=OUT/'iterations'/('before-usb-reserve-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));snap.mkdir(parents=True)
for name in [FILE.name,'design.json']:shutil.copy2(OUT/name,snap/name)
b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()}
data=json.loads((OUT/'design.json').read_text(encoding='utf-8'))
before=sorted((f.GetReference(),d.GetNumber(),d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
moves={'R5':(18.25,46.5),'J22':(18.5,50.5),'R28':(28.5,44.75),'R29':(30.5,44.75)}
old={(d.GetPosition().x,d.GetPosition().y) for ref in moves for d in fps[ref].Pads()}
reset={'M_USB_DP','M_USB_DM','ESP_USB_DM19','ESP_USB_DP20'}
held=[];removed=[]
for t in list(b.GetTracks()):
    incident=not isinstance(t,p.PCB_VIA) and any((q.x,q.y) in old for q in [t.GetStart(),t.GetEnd()])
    if t.GetNetname() in reset or incident:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});held.append(t);b.Remove(t)
for ref,(x,y) in moves.items():fps[ref].SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)))
assert before==sorted((f.GetReference(),d.GetNumber(),d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
for q in data['parts']:
    f=fps[q['ref']];q.update(x=p.ToMM(f.GetPosition().x),y=p.ToMM(f.GetPosition().y),angle=f.GetOrientationDegrees(),side='B' if f.GetLayer()==p.B_Cu else 'F')
data.setdefault('two_layer_iterations',[]).append({'snapshot':str(snap.relative_to(OUT)),
    'reason':'USB header/host straps nearer ESP, clear of rear boost/charger pads; GPIO4 pull-down nearer ESP', 'moves':moves})
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(OUT/'exports/usb-reserve-relocation.json').write_text(json.dumps({'moves':moves,'removed_routes':removed,'USB_impedance_qualified':False},indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Moved USB reserve and GPIO4 pull-down with complete net contract preserved.')
