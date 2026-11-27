"""Remove redundant ground routing in an isolated, refilled candidate.

Preserve local power/amp loops and short pad/via necks. Ground vias and the
isolated CELL_NEG protection return remain. Final DRC/connectivity required.
"""
import collections,hashlib,json,math,sys
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parents[1]/'build/v7-back-routes-20261124'
FILE=OUT/'voice_mainboard_v7.kicad_pcb'
b=p.LoadBoard(str(FILE))
def xy(v):return p.ToMM(v.x),p.ToMM(v.y)
# Keep local returns around the modem and ESP buck, boost, charger, battery
# protector, power mux, amp and cell undervoltage supervisor.
local_boxes=[(42,-.1,56,17),(21,22,35,36),(24,57,40,70),
             (36,48,48,62),(11,58,24,69),(47,56,60,69),
             (86,14,97,27),(20,50,28,60)]
points=[xy(pd.GetPosition())for fp in b.GetFootprints()for pd in fp.Pads()if pd.GetNetname()=='GND']
points.extend(xy(t.GetPosition()) for t in b.GetTracks()if isinstance(t,p.PCB_VIA) and t.GetNetname()=='GND')
changes=[];held=[];before={};after={}
for layer in [p.F_Cu,p.B_Cu]:
    before[b.GetLayerName(layer)]=sum(not isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND'and t.GetLayer()==layer for t in b.GetTracks())
for t in list(b.GetTracks()):
    if isinstance(t,p.PCB_VIA)or t.GetNetname()!='GND':continue
    a,z=xy(t.GetStart()),xy(t.GetEnd());length=p.ToMM(t.GetLength())
    local=any(all(x0<=q[0]<=x1 and y0<=q[1]<=y1 for q in [a,z])for x0,y0,x1,y1 in local_boxes)
    neck=length<=2 and any(math.dist(q,a)<=.15 or math.dist(q,z)<=.15 for q in points)
    if local or neck:continue
    changes.append({'uuid':t.m_Uuid.AsString(),'layer':b.GetLayerName(t.GetLayer()),'start':a,'end':z,'width_mm':p.ToMM(t.GetWidth()),'length_mm':length})
    held.append(t);b.Remove(t)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for layer in [p.F_Cu,p.B_Cu]:
    after[b.GetLayerName(layer)]=sum(not isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND'and t.GetLayer()==layer for t in b.GetTracks())
report={'date':'2026-11-24','candidate_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'before_ground_segments':before,'after_ground_segments':after,'removed_length_mm':sum(c['length_mm']for c in changes),'preserved_local_boxes_mm':local_boxes,'ground_vias_retained':True,'cell_negative_unchanged':True,'changes':changes,'manufacturing_ready':False,'status':'Requires native DRC and review of remaining plane bridges.'}
(OUT/'ground-changes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for t in held:t.thisown=False
print(json.dumps({k:v for k,v in report.items()if k!='changes'},ensure_ascii=False,indent=2))
