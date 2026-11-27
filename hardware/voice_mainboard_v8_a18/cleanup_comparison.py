"""Correct generated escape-layer ownership and remove obsolete unused vias.

Do not suppress native DRC findings. A new report is required after this tool.
"""
from pathlib import Path
import json,os,math
import pcbnew as p
FILE=Path(os.environ['A18_REPAIR_BOARD']);ROOT=FILE.parent
b=p.LoadBoard(str(FILE));fps={f.GetReference():f for f in b.GetFootprints()};changes=[];held=[]
report_file=ROOT/'exports/local-escape-review.json'
if report_file.exists():
    for q in json.loads(report_file.read_text(encoding='utf-8')):
        if not q.get('success'):continue
        f=fps[q['pad'][0]];d=next(x for x in f.Pads()if x.GetNumber()==q['pad'][1]);target=q['via_mm']
        for t in b.GetTracks():
            if isinstance(t,p.PCB_VIA)or t.GetNetname()!=d.GetNetname():continue
            start=t.GetStart();end=t.GetEnd()
            if math.dist([p.ToMM(start.x),p.ToMM(start.y)],[p.ToMM(d.GetPosition().x),p.ToMM(d.GetPosition().y)])<.001 and math.dist([p.ToMM(end.x),p.ToMM(end.y)],target)<.001 and t.GetLayer()!=f.GetLayer():
                changes.append({'escape_layer_fixed':q['pad'],'uuid':str(t.m_Uuid.AsString())});t.SetLayer(f.GetLayer())
if os.environ.get('A18_REMOVE_DANGLING_FROM'):
    drc=json.loads(Path(os.environ['A18_REMOVE_DANGLING_FROM']).read_text(encoding='utf-8'))
    ids={q['items'][0]['uuid']for q in drc['violations']if q['type']=='via_dangling'}
    track_ids={q['items'][0]['uuid']for q in drc['violations']if q['type']=='track_dangling'}
    for t in list(b.GetTracks()):
        if isinstance(t,p.PCB_VIA)and str(t.m_Uuid.AsString())in ids:
            changes.append({'removed_unused_via':str(t.m_Uuid.AsString()),'net':t.GetNetname()});held.append(t);b.Remove(t)
        elif not isinstance(t,p.PCB_VIA)and str(t.m_Uuid.AsString())in track_ids:
            changes.append({'removed_unterminated_stub':str(t.m_Uuid.AsString()),'net':t.GetNetname()});held.append(t);b.Remove(t)
for d in fps['J11'].Pads():d.SetLocalZoneConnection(p.ZONE_CONNECTION_INHERITED)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'exports/cleanup-review.json').write_text(json.dumps(changes,indent=2),encoding='utf-8')
print('Explicit cleanup changes',len(changes))
for t in held:t.thisown=False
