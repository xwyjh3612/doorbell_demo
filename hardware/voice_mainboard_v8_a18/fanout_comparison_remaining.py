"""Escape only unresolved narrow pads to conventional off-pad through vias."""
from pathlib import Path
import json,os,sys,types,math
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=Path(os.environ['A18_REPAIR_BOARD']).resolve()
sys.argv=[__file__,str(file)]
source=(ROOT.parent/'voice_mainboard_v3/route_helpers.py').read_text(encoding='utf-8')
source=source.replace('    blocked=unary_union(all_obstacles);fblocked=unary_union(front)', '''    for z in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not z.GetIsRuleArea():continue
        for i in range(z.Outline().OutlineCount()):
            ring=z.Outline().COutline(i)
            shape=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
            all_obstacles.append(shape.buffer(diameter/2+.505))
            if z.IsOnLayer(layer):front.append(shape.buffer(neck/2+.205))
    blocked=unary_union(all_obstacles);fblocked=unary_union(front)''')
r=types.ModuleType('comparison_escape')
exec(compile(source,'comparison_escape','exec'),r.__dict__)
report=json.loads((file.parent/'imported-drc.json').read_text(encoding='utf-8'))
ids={i['uuid'] for q in report['unconnected_items']for i in q['items']}
parts={q['ref']:q for q in json.loads((file.parent/'design.json').read_text(encoding='utf-8'))['parts']}
power=['SYS_5V','MODEM_3V8','ESP_3V3','BAT_BOOST_5V','VIN_PROTECTED','BAT_SENSE_IN','CELL_NEG']
pairs=[]
for f in r.board.GetFootprints():
    for pad in f.Pads():
        if str(pad.m_Uuid.AsString())in ids and pad.GetAttribute()==p.PAD_ATTRIB_SMD:
            pairs.append((f.GetReference(),pad.GetNumber(),pad.GetNetname()))
entries=[]
for ref,num,net in sorted(pairs,key=lambda q:(q[2]not in power,q[0],q[1])):
    try:
        r.escapevia(f'escape_{ref}_{num}',(ref,num),diameter=.6 if net in power else .45,
                    drill=.3 if net in power else .2,neck=.16)
        pos=r.pos(r.virtual[f'escape_{ref}_{num}'])
        entry={'pad':[ref,num],'net':net,'success':True,'via_mm':pos,
               'short_neck_mm':math.dist(r.pos(r.pad(ref,num)),pos)}
    except RuntimeError as error:
        entry={'pad':[ref,num],'net':net,'success':False,'reason':str(error)}
    entries.append(entry)
    p.SaveBoard(str(file),r.board)
    print(entry,flush=True)
r.board.BuildConnectivity();assert p.ZONE_FILLER(r.board).Fill(r.board.Zones())
p.SaveBoard(str(file),r.board)
(file.parent/'remaining-pad-fanout.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
