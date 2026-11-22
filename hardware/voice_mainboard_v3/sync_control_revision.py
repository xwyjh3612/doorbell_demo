"""Apply a reviewed pin-compatible comparator swap without resetting routing.

U10 MODE is moved to the analog bias, then its obsolete direct VIN copper is
removed locally. Its new connection must be re-routed and pass DRC/ERC.
"""
from pathlib import Path
import json,sys,math
import pcbnew as p
root=Path(__file__).resolve().parent
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import Point,LineString
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
d=json.loads((root/'design.json').read_text(encoding='utf8'))
parts={f.GetReference():f for f in b.GetFootprints()}
for item in d['parts']:
    if item['ref']=='U11':
        item.update(value='LM393LVDGKR TI C3659248',source='https://www.ti.com/lit/ds/symlink/lm393lv.pdf',
          note='TI LV part only,1.65-5.5V rail-to-rail input,full-temperature offset+/-3mV,no specified internal hysteresis. C3659248 public1.0033CNY,stock1338 on20261122. Ordinary LM393 is not interchangeable.')
        parts['U11'].SetValue(item['value'])
    if item['ref']=='R42':item['value']='3.3k';parts['R42'].SetValue('3.3k')
    if item['ref']in ['R50','R51','R52']:
        item['value']={'R50':'54.9k 0.1%','R51':'10k 0.1%','R52':'3.9M 1%'}[item['ref']]
        parts[item['ref']].SetValue(item['value'])
    if item['ref']=='U12':
        item.update(value='TLV431BIDBZR TI C398375',source='https://www.ti.com/lit/ds/symlink/tlv431.pdf',note='B grade TI reference,0.5% initial; full-temperature I grade1.224-1.259V. C398375 public1.25CNY stock14109 on20261122.')
        parts['U12'].SetValue(item['value'])
    if item['ref']=='U10':
        item['pins']['5']='UPS_CTL_VCC'
        item['note']='Comparator-driven manual selection, MODE biased from diode-OR UPS_CTL_VCC; stays high after external input is lost.'
mode=next(pd for pd in parts['U10'].Pads()if pd.GetNumber()=='5')
changed=mode.GetNetname()!='UPS_CTL_VCC'
removed=[]
if changed:
    point=Point(p.ToMM(mode.GetPosition().x),p.ToMM(mode.GetPosition().y))
    for t in list(b.GetTracks()):
        if t.GetNetname()!='VIN_PROTECTED':continue
        if isinstance(t,p.PCB_VIA):shape=Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y))
        else:shape=LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))])
        if shape.distance(point)<.7:removed.append(t);b.Remove(t)
    mode.SetNet(b.FindNet('UPS_CTL_VCC'))
d['ups_controls']['comparator']={'part':'LM393LVDGKR','lcsc':'C3659248','supply_range_v':[1.65,5.5],
 'rail_to_rail_input':True,'output':'open-drain','offset_full_temperature_v':[-.003,.003],'internal_hysteresis_specified':False}
d['ups_controls']['reference_bias_ohm']=3300
d['ups_controls']['external_priority'].update(top_ohm=54900,bottom_ohm=10000,feedback_ohm=3900000)
d['ups_controls']['reference_part']='TLV431BIDBZR C398375'
d['ups_controls']['mux_mode']='external comparator selection, MODE=UPS_CTL_VCC'
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(root/'exports/control-revision.json').write_text(json.dumps({'comparator':'TI LM393LVDGKR','same_DGK_footprint':True,
 'reference_bias_ohm':3300,'MODE_new_net':'UPS_CTL_VCC','old_MODE_VIN_local_copper_removed':len(removed),'DRC_and_new_MODE_connection_required':True},indent=2)+'\n',encoding='utf8')
print('Synchronized control part revision; removed MODE old VIN copper:',len(removed))
