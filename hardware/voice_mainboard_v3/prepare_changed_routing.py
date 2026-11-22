"""Remove only copper conflicting with changed placement, then refill ground.

Existing copper uses V2's fine-drill vias. The standard-drill conversion and
final critical power routing are separate checks, not assumed by this step.
"""
from pathlib import Path
import json,sys
import pcbnew as pcb
ROOT=Path(__file__).resolve().parent
boardfile=ROOT/'voice_mainboard_v3.kicad_pcb'
board=pcb.LoadBoard(str(boardfile))
footprints={f.GetReference():f for f in board.GetFootprints()}
tracks={str(t.m_Uuid.AsString()):t for t in board.GetTracks()}
drc=json.loads((ROOT/'exports/current-drc.json').read_text(encoding='utf8'))
removed=set()
for v in drc['violations']:
    if v['type'] not in ['clearance','shorting_items','solder_mask_bridge','hole_clearance','hole_to_hole']:continue
    for item in v['items']:
        uid=item['uuid']
        if uid in tracks:removed.add(uid)
for uid in removed:board.Remove(tracks[uid])
# Rebuild, rather than append overlapping copies of the review planes.
old_zones=list(board.Zones())
for zone in old_zones:board.Remove(zone)
sys.path.insert(0,str(ROOT.parent/'voice_mainboard_v2'))
from fill_review_planes import fill
fill(board)
pcb.SaveBoard(str(boardfile),board)
(ROOT/'exports/changed-copper-prune.json').write_text(json.dumps({'removed_copper_uuids':sorted(removed),'removed_items':len(removed),'ground_refilled':True,'route_complete':False},indent=2)+'\n',encoding='utf8')
print('Removed obsolete crossing copper',len(removed),'items; ground refilled.')
