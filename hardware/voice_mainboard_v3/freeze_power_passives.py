"""Apply specific power passives and their reviewed package dimensions.

The saved PCB is revised, not regenerated. Converter load/thermal and real
switching behavior remain prototype acceptance requirements.
"""
from pathlib import Path
import json,math
import pcbnew as p
root=Path(__file__).resolve().parent
candidate=p.FootprintLoad(str(Path('build/cad-tools/kicad/share/kicad/footprints/Capacitor_SMD.pretty').resolve()),'CP_Elec_10x10')
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'));d=json.loads((root/'design.json').read_text(encoding='utf8'));fps={f.GetReference():f for f in b.GetFootprints()};held=[]
def part(ref,mpn,sku,url,price,note):
    item=next(v for v in d['parts']if v['ref']==ref);item.update(mpn=mpn,lcsc=sku,source=url,unit_public_reference_cny=price,note=note)
    fps[ref].SetValue(mpn+' '+sku);item['value']=fps[ref].GetValue()
for ref in ['C8','C9']:
    part(ref,'APXE6R3ARA221MF61G','C2161900','https://item.szlcsc.com/2253950.html',5.23,'NCC PXE datasheet terminal A/F61: D6.3,L5.8,A/B6.6,C7.2,P1.9. 220u6.3V +/-20%; exact row ESR/ripple and stencil checked separately. Public stock94 on20261122; batch procurement must be quoted, not assumed available in1000pcs.')
part('L1','SWPA6045S2R2MT','C83455','https://item.szlcsc.com/84619.html',.2756,'Sunlord SWPA catalog2025/5/8 page13:2.2uH+/-20%,DCR18mOhm max,Isat6.75A rated,Irms4.6A rated. Standard SWPA6045S land. Public stock21; qty100/1000 need procurement lead-time quote.')
part('L2','SWPA6045S1R5MT','C98203','https://item.szlcsc.com/99412.html',.2862,'Sunlord SWPA catalog2025/5/8 page13:1.5uH+/-20%,DCR16mOhm max,Isat8.2A rated,Irms5.45A rated. Standard SWPA6045S land. Public stock73; qty100/1000 need procurement lead-time quote.')
for item in d['parts']:
    if item['footprint']=='Capacitor_SMD:C_0805_2012Metric'and item['value'].startswith('22u'):
        part(item['ref'],'CL21A226MOCLRNC','C398815','https://item.szlcsc.com/381139.html',.2619,'Samsung22u16V X5R0805 +/-20%; replaces nominal22u10V/16V entries. Actual DC-bias effective capacitance and converter acceptance remain required. Public stock16580 on20261122.')
# The selected 470uF polymer is D10mm, not the former generic D8 candidate.
if fps['C48'].GetFPID().GetLibItemName()!='CP_Elec_10x10':
    old=fps['C48'];centers=[(p.ToMM(pd.GetPosition().x),p.ToMM(pd.GetPosition().y))for pd in old.Pads()];held.append(old);b.Remove(old)
    for t in list(b.GetTracks()):
        if isinstance(t,p.PCB_VIA):continue
        endpoints=[(p.ToMM(pt.x),p.ToMM(pt.y))for pt in [t.GetStart(),t.GetEnd()]]
        if any(math.dist(a,z)<.1 for a in endpoints for z in centers):held.append(t);b.Remove(t)
    fp=candidate;fp.SetReference('C48');fp.SetPosition(p.VECTOR2I(p.FromMM(23.75),p.FromMM(69)))
    for pd in fp.Pads():pd.SetNet(b.FindNet('POWER_REG_5V'if pd.GetNumber()=='1'else'GND'))
    fp.Reference().SetLayer(p.F_Fab);fp.Value().SetVisible(False);b.Add(fp);fps['C48']=fp
    item=next(v for v in d['parts']if v['ref']=='C48');item.update(footprint='Capacitor_SMD:CP_Elec_10x10',x=23.75,y=69,angle=0)
part('C48','OCV471M1ATR-1010','C250035','https://item.szlcsc.com/246157.html',1.1262,'Lelon OCV2025E3 page30:470u10V +/-20%,D10xL9.9mm, ESR18mOhm max at100-300kHz/20C, ripple4.4Arms at105C. Base/land reviewed against package table. Public stock1778 on20261122. Converter and switch hold-up qualification still required.')
# Keep R41 physically clear of the enlarged front-side capacitor body.
f=fps['R41']
if f.GetLayer()!=p.B_Cu:
    for t in list(b.GetTracks()):
        if t.GetNetname()=='UPS_BOOST_FB':held.append(t);b.Remove(t)
    f.Flip(f.GetPosition(),True);f.SetPosition(p.VECTOR2I(p.FromMM(19),p.FromMM(62.75)))
    item=next(v for v in d['parts']if v['ref']=='R41');item.update(x=19,y=62.75,side='B',angle=f.GetOrientationDegrees())
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Applied specific power passives; reroute/DRC required after C48/R41 changes')
