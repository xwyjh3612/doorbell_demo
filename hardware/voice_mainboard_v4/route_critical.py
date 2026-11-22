"""Route power switching nodes locally before signal autorouting.

Uses collision-aware geometry helper, then relies on native KiCad DRC. This
does not certify control-loop stability or current/thermal qualification.
"""
from pathlib import Path
import importlib.util,sys,json
import pcbnew as p
ROOT=Path(__file__).resolve().parent
boardfile=ROOT/'voice_mainboard_v4.kicad_pcb'
sys.argv=[__file__,str(boardfile)]
spec=importlib.util.spec_from_file_location('routing',ROOT.parent/'voice_mainboard_v3/route_helpers.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
pairs=[
 (('U2',5),('L1',1),.8,(26,42,37,52)),
 (('U2',6),('C3',1),.2,(26,40,33,49)),
 (('C3',2),('L1',1),.3,(27,40,37,52)),
 (('L1',2),('C6',1),.9,(31,42,40,52)),
 (('L1',2),('C7',1),.9,(31,42,40,54)),
 (('U2',3),('C4',1),.45,(22,44,29,50)),
 (('C4',1),('C5',1),.8,(21,44,27,55)),
 (('U13',3),('L4',1),.65,(27,25,37,32)),
 (('L4',2),('C60',1),.8,(30,25,40,33)),
 (('U13',4),('C59',1),.45,(21,25,30,33)),
 (('U13',1),('C59',1),.2,(21,25,30,33)),
 (('U9',5),('L3',2),.9,(79,3,92,15)),
 (('U9',2),('U9',4),.2,(79,9,90,17)),
 (('U9',4),('C41',1),.45,(77,9,90,17)),
 (('C41',1),('L3',1),.85,(76,1,93,17)),
 (('U9',7),('C42',1),.7,(82,8,94,16)),
 (('C42',1),('C43',1),.9,(85,8,98,15)),
 (('U9',1),('C45',1),.2,(81,10,91,17)),
 (('C45',2),('C42',1),.2,(83,9,93,18)),
]
records=[]
for a,b,width,bounds in pairs:
    try:
        r.route(a,b,width=width,step=.04,bounds=bounds)
        records.append({'from':a,'to':b,'width_mm':width,'routed':True})
    except RuntimeError as e:
        records.append({'from':a,'to':b,'width_mm':width,'routed':False,'reason':str(e)})
        print('Pending critical connection:',a,b,str(e),flush=True)
for t in r.board.GetTracks():t.SetLocked(True)
p.SaveBoard(str(boardfile),r.board)
(ROOT/'exports/critical-routing.json').write_text(json.dumps({'connections':records,'load_qualified':False},indent=2)+'\n',encoding='utf8')
print('Critical local routes:',sum(q['routed'] for q in records),'/',len(records),flush=True)
