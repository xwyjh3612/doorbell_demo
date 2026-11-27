"""Rip up native-reported copper conflicts at relocated supply components."""
from pathlib import Path
import os,json
import pcbnew as p
FILE=Path(os.environ['A18_REPAIR_BOARD']);ROOT=FILE.parent;b=p.LoadBoard(str(FILE))
report=json.loads(Path(os.environ['A18_FINISH_DRC']).read_text(encoding='utf-8'))
padids={str(d.m_Uuid.AsString())for f in b.GetFootprints()if f.GetReference()in ['U18','R70','R71','C71','C72','U15','C66','R72','TP12','C15','Q2','C19','R75','R8']for d in f.Pads()}
lockedids={str(t.m_Uuid.AsString())for t in b.GetTracks()if t.IsLocked()}
trackids={i['uuid']for q in report['violations']if any(i['uuid']in padids|lockedids for i in q['items'])and q['type']in ['clearance','hole_clearance','shorting_items','solder_mask_bridge','tracks_crossing']for i in q['items']}
held=[];changes=[]
for t in list(b.GetTracks()):
    if str(t.m_Uuid.AsString())in trackids and not t.IsLocked():
        changes.append({'uuid':str(t.m_Uuid.AsString()),'net':t.GetNetname()});held.append(t);b.Remove(t)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'exports/moved-pad-conflict-ripup.json').write_text(json.dumps(changes,indent=2),encoding='utf-8');print('Ripped up copper conflicts',len(changes))
for t in held:t.thisown=False
