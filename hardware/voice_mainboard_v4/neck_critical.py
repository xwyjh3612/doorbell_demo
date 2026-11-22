"""Escape fine-pitch power pads before widening; run after route_critical."""
from pathlib import Path
import importlib.util,sys,json
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
sys.argv=[__file__,str(file)]
spec=importlib.util.spec_from_file_location('r',ROOT.parent/'voice_mainboard_v3/route_helpers.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
tasks=[
 (('U2',5),(29.8,47.75),('L1',1),.8,(27,43,37,51)),
 (('U2',3),(26.1,47.25),('C4',1),.55,(21,43,29,51)),
 (('U9',5),(82.9,11.5),('L3',2),.75,(78,1,92,16)),
 (('U9',4),(86.95,10.6),('C41',1),.5,(76,8,92,17)),
 (('U9',7),(84.4,13.25),('C42',1),.6,(80,8,98,18))]
records=[]
for i,(start,xy,end,width,bounds) in enumerate(tasks):
    net=r.pad(*start).GetNetname();ref='NECK'+str(i)
    r.virtual[ref]=r.Endpoint(net,xy)
    try:
        r.route(start,(ref,1),width=.25 if start[0]=='U2' else .2,step=.025,bounds=bounds)
        r.route((ref,1),end,width=width,step=.04,bounds=bounds)
        records.append({'from':start,'to':end,'neck_mm':.25 if start[0]=='U2' else .2,'trunk_mm':width,'routed':True})
    except RuntimeError as e:records.append({'from':start,'to':end,'routed':False,'reason':str(e)})
for t in r.board.GetTracks():t.SetLocked(True)
p.SaveBoard(str(file),r.board)
(ROOT/'exports/critical-necks.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf8')
print(records)
