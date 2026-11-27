"""Reroute new LED supply while preserving the U4 ground escape corridor."""
import hashlib,json,sys,types
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'indicator_revision';FILE=OUT/'voice_mainboard_v7.kicad_pcb'
src=(ROOT/'add_indicator_candidate.py').read_text(encoding='utf-8')
start=src.index('source=(ROOT.parent/');end=src.index('data=json.loads(')
setup='import collections,hashlib,json,re,shutil,sys,types,uuid\nfrom pathlib import Path\nimport pcbnew as p\nROOT=Path(__file__).resolve().parent\nREPO=ROOT.parents[1]\nOUT=ROOT/"indicator_revision"\nFILE=OUT/"voice_mainboard_v7.kicad_pcb"\n'+src[start:end]
setup=setup.replace("m=types.ModuleType('led_multilayer');",'''multi=multi.replace("        shapes=[]", "        shapes=[]\\n        if net=='ESP_3V3' and layer==p.F_Cu:shapes.append(Polygon([(43.7,24.2),(46.1,24.2),(46.1,26.3),(43.7,26.3)]).buffer(clearance))")
m=types.ModuleType('led_multilayer');''')
mod=types.ModuleType('rgb_supply');mod.__dict__['__file__']=__file__;exec(compile(setup,'rgb_supply_helpers','exec'),mod.__dict__)
r=mod.r;b=r.board;held=[]
old=p.LoadBoard(str(ROOT/FILE.name));oldids={t.m_Uuid.AsString()for t in old.GetTracks()}
def inside(v):return 68<=p.ToMM(v.x)<=80 and 0<=p.ToMM(v.y)<=9
for t in list(b.GetTracks()):
    if t.GetNetname()!='ESP_3V3' or t.m_Uuid.AsString()in oldids:continue
    keep=inside(t.GetPosition())if isinstance(t,p.PCB_VIA)else inside(t.GetStart())and inside(t.GetEnd())
    if not keep:held.append(t);b.Remove(t)
vs=[t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.GetNetname()=='ESP_3V3']
r.virtual['led_supply_source']=min(vs,key=lambda t:(r.pos(t)[0]-71.1)**2+(r.pos(t)[1]-4.5)**2)
r.virtual['led_supply_target']=min(vs,key=lambda t:(r.pos(t)[0]-46.1)**2+(r.pos(t)[1]-19)**2)
mod.m.route(r,('led_supply_source',0),('led_supply_target',0),width=.2,step=.1,bounds=(1,1,98,73.4))
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
(OUT/'exports/supply-corridor-changes.json').write_text(json.dumps({'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'removed_new_copper':len(held),'old_copper_preserved':True,'U4_ground_corridor_reserved_on_front':True},indent=2)+'\n',encoding='utf-8')
