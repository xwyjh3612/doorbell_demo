"""Restore two local pad-to-plane returns and remove three unused GND stubs."""
import json,sys,types,hashlib
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parents[1]/'build/v7-back-routes-20261124'
FILE=OUT/'voice_mainboard_v7.kicad_pcb'
source=(ROOT.parent/'voice_mainboard_v3/route_helpers.py').read_text(encoding='utf-8')
source=source.replace('    blocked=unary_union(all_obstacles);fblocked=unary_union(front)', '''    for zone in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not zone.GetIsRuleArea():continue
        for zi in range(zone.Outline().OutlineCount()):
            ring=zone.Outline().COutline(zi)
            sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
            all_obstacles.append(sh.buffer(diameter/2+.005))
            if zone.IsOnLayer(layer):front.append(sh.buffer(neck/2+.005))
    blocked=unary_union(all_obstacles);fblocked=unary_union(front)''')
sys.argv=[__file__,str(FILE)]
r=types.ModuleType('ground_returns');exec(compile(source,'ground_returns','exec'),r.__dict__)
b=r.board;held=[];changes=[]
report=json.loads((OUT/'ground-drc.json').read_text(encoding='utf-8'))
stubs={i['uuid']for v in report['violations']if v['type']=='track_dangling'for i in v['items']}
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString()in stubs:
        changes.append({'removed_stub':t.m_Uuid.AsString(),'net':t.GetNetname()});held.append(t);b.Remove(t)
for ref in ['C10','Q7']:
    r.escapevia('ground_'+ref,(ref,2),diameter=.6,drill=.3,neck=.25)
    changes.append({'local_ground_return':ref,'pad':2,'via_position_mm':r.pos(r.virtual['ground_'+ref]),'neck_mm':.25,'diameter_drill_mm':[.6,.3]})
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
(OUT/'ground-return-changes.json').write_text(json.dumps({'changes':changes,'candidate_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(changes,ensure_ascii=False,indent=2))
