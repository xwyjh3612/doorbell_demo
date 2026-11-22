"""Remove reported stale tails/conflicts without weakening design rules."""
from pathlib import Path
import json
import pcbnew as p
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
d=json.loads((root/'exports/current-drc.json').read_text(encoding='utf8'))
tracks={t.m_Uuid.AsString():t for t in b.GetTracks()};removed=[];held=[]
for v in d['violations']:
    if v['type']not in ['items_not_allowed','clearance','shorting_items','track_dangling','via_dangling']:continue
    for item in v['items']:
        t=tracks.pop(item['uuid'],None)
        if t is None:continue
        assert t.GetNetname()not in ['RF_ANT','RF_FEED','M_USB_DP','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19'],'Critical geometry needs explicit review'
        held.append(t);removed.append({'type':v['type'],'net':t.GetNetname(),'uuid':item['uuid']});b.Remove(t)
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'exports/stale-copper-prune.json').write_text(json.dumps(removed,indent=2)+'\n',encoding='utf8')
print('Removed reported stale copper:',len(removed))
