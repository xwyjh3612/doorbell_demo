"""Apply input parts with a specified on-resistance below the 4.5V boundary.

DMP2035U specifies 45mOhm maximum at VGS=-2.5V. The former AO4409
candidate only specified -4.5V, which was insufficient after input path loss.
"""
from pathlib import Path
import json
import pcbnew as p
candidate=p.FootprintLoad(str(Path('build/cad-tools/kicad/share/kicad/footprints/Package_TO_SOT_SMD.pretty').resolve()),'SOT-23')
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
d=json.loads((root/'design.json').read_text(encoding='utf8'));fps={f.GetReference():f for f in b.GetFootprints()}
if fps['Q6'].GetValue()!='DMP2035U-7 C110499':
    old=fps['Q6'];old_tracks=list(b.GetTracks());b.Remove(old)
    for t in old_tracks:
        if t.GetNetname()in ['VIN_FUSED','REVERSE_GATE']:b.Remove(t)
        elif t.GetNetname()=='VIN_PROTECTED'and 20<p.ToMM(t.GetStart().x)<28 and 20<p.ToMM(t.GetStart().y)<27:b.Remove(t)
    fp=candidate
    fp.SetReference('Q6');fp.SetValue('DMP2035U-7 C110499');fp.SetPosition(p.VECTOR2I(p.FromMM(27),p.FromMM(24)))
    pins={'1':'REVERSE_GATE','2':'VIN_PROTECTED','3':'VIN_FUSED'}
    for pd in fp.Pads():pd.SetNet(b.FindNet(pins[pd.GetNumber()]))
    fp.Reference().SetLayer(p.F_Fab);fp.Value().SetVisible(False);b.Add(fp)
    item=next(x for x in d['parts']if x['ref']=='Q6')
    item.update(value=fp.GetValue(),footprint='Package_TO_SOT_SMD:SOT-23',pins=pins,x=27,y=24,angle=0,
      names={'1':['G','input'],'2':['S','passive'],'3':['D','passive']},
      source='https://www.diodes.com/assets/Datasheets/DMP2035U.pdf',note='Diodes DMP2035U-7 C110499. SOT23 G1/S2/D3. RDS(on)max45mOhm at VGS=-2.5V,35mOhm at-4.5V. Public0.3881CNY stock215547 on20261122. Low-input gate drive is covered by -2.5V specification. Hot resistance/current/PCB thermal behavior need prototype verification. TPS2117 supplies source isolation; this FET only protects reversed adapter polarity.')
    progress=root/'exports/power-trunks.json';v=json.loads(progress.read_text(encoding='utf8'))
    v['branches']=[x for x in v['branches']if x['from'][0]!='Q6'and x['to'][0]!='Q6'];v['escape_vias']={key:val for key,val in v['escape_vias'].items()if not key.startswith('Q6/')};progress.write_text(json.dumps(v,indent=2)+'\n',encoding='utf8')
f=fps['F1'];f.SetValue('ASMD1812-400-16V C55014590')
item=next(x for x in d['parts']if x['ref']=='F1');item.update(value=f.GetValue(),mpn='ASMD1812-400-16V',lcsc='C55014590',unit_public_reference_cny=.4972,source='https://item.szlcsc.com/58601642.html',note='JDT ASMD1812-400-16V C55014590. Ihold4A/Itrip8A at25C; R1max25mOhm. 4A is the PTC rating for temperature derating; system input design baseline remains5V/2A. Datasheet thermal derating and adapter short-circuit protection require prototype validation. Public0.4972CNY stock2626 on20261122.')
# Existing PCB jack silk came from the superseded footprint version.
for sh in list(fps['J1'].GraphicalItems()):
    if sh.GetLayer()==p.F_SilkS:fps['J1'].Remove(sh)
p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Applied input MOSFET/fuse package revision; re-route before release')
