"""Keep input protection out of the RF reference area; shorten RF shunts.

This placement refinement is not an impedance qualification. Preserve real
pad geometry and DNP choices; rebuild the affected nets and rerun native DRC.
"""
from pathlib import Path
import datetime, json, shutil
import pcbnew as p
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'two_layer_work'; FILE = OUT / 'voice_mainboard_a18_2layer.kicad_pcb'
snap = OUT / 'iterations' / ('before-rf-reference-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snap.mkdir(parents=True)
for name in [FILE.name, 'design.json']:
    shutil.copy2(OUT / name, snap / name)
b = p.LoadBoard(str(FILE)); fps = {f.GetReference(): f for f in b.GetFootprints()}
data = json.loads((OUT / 'design.json').read_text(encoding='utf-8'))
parts = {q['ref']:q for q in data['parts']}
before = sorted((f.GetReference(),d.GetNumber(),d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
held = []; removed = []
for t in list(b.GetTracks()):
    if t.GetNetname() in ['VIN_DC','VIN_FUSED','RF_ANT','RF_FEED']:
        removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()})
        held.append(t); b.Remove(t)
moves = {'F1':(61.5,45.5,90), 'C24':(64.5,17.65,90), 'C25':(66.5,19.15,90)}
for ref,(x,y,angle) in moves.items():
    f = fps[ref];f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));f.SetOrientationDegrees(angle)
    parts[ref].update(x=x,y=y,angle=angle)
    parts[ref]['note'] = parts[ref].get('note','') + ' A18 two-layer RF-reference refinement; impedance review pending.'

# Give the two-layer U.FL keepout its own explicit library identity.
name = 'UFL_Hirose_2Layer_A18'
template = p.FootprintLoad(str(ROOT.parents[1]/'build/cad-tools/kicad/share/kicad/footprints/Connector_Coaxial.pretty'), 'U.FL_Hirose_U.FL-R-SMT-1_Vertical')
mask = p.LSET();mask.AddLayer(p.F_Cu);mask.AddLayer(p.B_Cu)
for z in template.Zones():z.SetLayerSet(mask)
template.SetFPID(p.LIB_ID('VoiceV2',name));p.FootprintSave(str(ROOT/'VoiceV2.pretty'),template)
old = fps['J11'];new = p.FootprintLoad(str(ROOT/'VoiceV2.pretty'),name)
new.SetFPID(p.LIB_ID('VoiceV2',name));new.SetPosition(old.GetPosition());new.SetOrientationDegrees(old.GetOrientationDegrees())
geometry = lambda f: sorted((d.GetNumber(),d.GetPosition().x,d.GetPosition().y,d.GetSize().x,d.GetSize().y) for d in f.Pads())
assert geometry(old)==geometry(new),'Do not change Hirose pad geometry'
new.SetReference(old.GetReference());new.SetValue(old.GetValue());new.SetPath(old.GetPath())
for field,newfield in [(old.Reference(),new.Reference()),(old.Value(),new.Value())]:
    newfield.SetLayer(field.GetLayer());newfield.SetPosition(field.GetPosition());newfield.SetTextSize(field.GetTextSize());newfield.SetTextThickness(field.GetTextThickness());newfield.SetVisible(field.IsVisible())
for d in new.Pads():d.SetNet(b.FindNet('RF_FEED' if d.GetNumber()=='1' else 'GND'))
b.Remove(old);held.append(old);b.Add(new)
oldid=parts['J11']['footprint'];parts['J11']['footprint']='VoiceV2:'+name
sch=FILE.with_suffix('.kicad_sch');text=sch.read_text(encoding='utf-8')
at=text.rindex(oldid);text=text[:at]+'VoiceV2:'+name+text[at+len(oldid):];sch.write_text(text,encoding='utf-8')
after=sorted((f.GetReference(),d.GetNumber(),d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
assert before==after
data.setdefault('two_layer_iterations',[]).append({'snapshot':str(snap.relative_to(OUT)),
    'moves':moves,'reason':'Input fuse moved near DC entry to clear RF backside reference; RF matching footprints moved closer to feed; pad nets/DNP/BOM quantity unchanged.'})
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(OUT/'exports/rf-reference-refinement.json').write_text(json.dumps({'moves':moves,'removed_routes':removed,'impedance_qualified':False},indent=2),encoding='utf-8')
for item in held:item.thisown=False
print('Moved input fuse and RF shunts; affected input/RF routes must be rebuilt and native checks rerun.')
