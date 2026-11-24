"""Keep intentional board-only holes/test pads in a matching project library."""
from pathlib import Path
import json,pcbnew as p
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
b=p.LoadBoard(str(FILE));d=json.loads((ROOT/'design.json').read_text(encoding='utf8'));parts={q['ref']:q for q in d['parts']}
for f in b.GetFootprints():
    ref=f.GetReference()
    if not ref.startswith(('TP','H')):continue
    f.SetAttributes(f.GetAttributes()|p.FP_EXCLUDE_FROM_BOM|p.FP_EXCLUDE_FROM_POS_FILES)
    name='V6_BOARD_'+ref;libid=p.LIB_ID('VoiceV2',name)
    copy=p.FOOTPRINT(f);copy.SetOrientationDegrees(0);copy.SetPosition(p.VECTOR2I(0,0));copy.SetFPID(libid)
    copy.SetReference('REF**');copy.SetValue(name);copy.SetPath(p.KIID_PATH())
    for pad in copy.Pads():pad.SetNetCode(0)
    copy.SetLibDescription('Project copper test point / board mounting hole. No purchased component. Geometry preserved from saved board; intentional board-only BOM/PnP attributes.')
    p.FootprintSave(str(ROOT/'VoiceV2.pretty'),copy)
    f.SetFPID(libid);parts[ref]['footprint']='VoiceV2:'+name
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
p.SaveBoard(str(FILE),b)
