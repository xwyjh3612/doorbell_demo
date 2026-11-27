"""Replace the existing fixed zero-ohm audio straps with equivalent copper.

R76 already shorts GAIN to ground (12 dB); R75 already shorts SD_MODE to SYS_5V
(left channel). Keep those functions, remove two parts, and update the actual
schematic and board together. This is an isolated engineering trial.
"""
import datetime
import json
import re
import shutil
from comparison_route_geometry import b,FILE,p,pos,route

fps={f.GetReference():f for f in b.GetFootprints()}
for ref in ['R75','R76']:assert fps[ref].GetValue().startswith('0R')
snapshot=FILE.parent/'iterations'/('before-fixed-audio-straps-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
for f in [FILE,FILE.with_suffix('.kicad_sch'),FILE.parent/'design.json']:shutil.copy2(f,snapshot/f.name)
contract={ref:{d.GetNumber():d.GetNetname()for d in fps[ref].Pads()}for ref in ['R75','R76']}
assert contract=={'R75':{'1':'SYS_5V','2':'AMP_SD'},'R76':{'1':'AMP_GAIN','2':'GND'}}
held=[]
for t in list(b.GetTracks()):
    if t.GetNetname()in('AMP_GAIN','AMP_SD'):b.Remove(t);held.append(t)
for ref in ['R75','R76']:b.Remove(fps[ref]);held.append(fps[ref])
pads={d.GetNumber():d for d in fps['U14'].Pads()}
assert pads['2'].GetNetname()=='AMP_GAIN'and pads['4'].GetNetname()=='AMP_SD'
pads['2'].SetNet(b.FindNet('GND'));pads['4'].SetNet(b.FindNet('SYS_5V'))
ground=route('GND',pos(pads['2']),pos(pads['3']),{0},{0},width=.16,step=.025,bounds=(32,48,35,50))
select=route('SYS_5V',pos(pads['4']),pos(pads['7']),{0},{0},width=.16,step=.025,bounds=(29,48,37,54))

def spans(text):
    depth=0;quoted=False;escaped=False;start=None;out=[]
    for i,ch in enumerate(text):
        if quoted:
            if escaped:escaped=False
            elif ch=='\\':escaped=True
            elif ch=='"':quoted=False
            continue
        if ch=='"':quoted=True
        elif ch=='(':
            if depth==1:start=i
            depth+=1
        elif ch==')':
            depth-=1
            if depth==1 and start is not None:out.append((start,i+1));start=None
    return out
sch=FILE.with_suffix('.kicad_sch');text=sch.read_text(encoding='utf-8')
removed_ids={'2bd07e90-cf4c-57c7-9d77-d25faf67bec2','7f58b20d-280d-52f4-a9cc-535117ad754d',
 '7d8719a9-bdf3-5f80-a24a-8d937fc60697','28a1f84a-a164-5747-9853-5a117bc35400',
 'f90223b9-a12a-507d-b405-76c6f3e4c704','51a56657-7d4f-5510-9c99-9dae5fe20bca',
 'a73f32c6-817b-5415-954e-0e9c9d57d4ed','264a6b4a-40bd-52c1-9141-e64a77266d54'}
retire=[]
for a,z in spans(text):
    block=text[a:z]
    if any('(uuid '+u+')'in block for u in removed_ids)or any(block.startswith('(symbol (lib_id "VoiceV2:'+ref+'")')for ref in['R75','R76']):retire.append((a,z))
assert len(retire)==10
for a,z in reversed(retire):text=text[:a]+text[z:]
assert text.count('(global_label "AMP_GAIN"')==text.count('(global_label "AMP_SD"')==1
text=text.replace('(global_label "AMP_GAIN"','(global_label "GND"').replace('(global_label "AMP_SD"','(global_label "SYS_5V"')
sch.write_text(text,encoding='utf-8')
designfile=FILE.parent/'design.json';design=json.loads(designfile.read_text(encoding='utf-8'))
design['parts']=[q for q in design['parts']if q['ref']not in('R75','R76')]
for q in design['parts']:
    if q['ref']=='U14':
        q['pins']['2']='GND';q['pins']['4']='SYS_5V'
        q['note']=q.get('note','')+' Fixed12dB/left-channel zero-ohm straps replaced by equivalent short copper; original functions retained.'
design['fixed_audio_straps']={'gain_db':12,'channel':'left','gain_pin':'U14.2 -> GND','select_pin':'U14.4 -> SYS_5V',
    'removed_zero_ohm_refs':['R75','R76'],'previous_pin_contract':contract,'assembly_parts_reduction':2}
designfile.write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
report={'removed_refs':['R75','R76'],'previous_pin_contract':contract,'gain_db':12,'channel':'left',
 'new_pin_contract':{'U14.2':'GND','U14.4':'SYS_5V'},'ground_strap':ground,'select_strap':select,
 'snapshot':str(snapshot),'native_ERC_DRC_parity_required':True,'manufacturing_ready':False}
(FILE.parent/'exports/fixed-audio-straps.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
