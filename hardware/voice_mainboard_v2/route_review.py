"""Route reviewed local signal branches. Power/RF/USB are intentionally pending.

This adds real copper to the reproducible KiCad draft; CLI DRC is run afterwards.
It does not manufacture plots or infer regulator/impedance qualification.
"""
from pathlib import Path
import json
import math
import pcbnew as pcb

ROOT=Path(__file__).resolve().parent
boardfile=ROOT/'voice_mainboard_v2.kicad_pcb'
board=pcb.LoadBoard(str(boardfile))
parts={fp.GetReference():fp for fp in board.GetFootprints()}
report=[]

def pad(ref,number):
    return next(p for p in parts[ref].Pads() if p.GetNumber()==str(number))

def pos(p):
    return (pcb.ToMM(p.GetPosition().x),pcb.ToMM(p.GetPosition().y))

def point(p):
    return pcb.VECTOR2I(pcb.FromMM(p[0]),pcb.FromMM(p[1]))

def track(a,b,net,layer,width):
    t=pcb.PCB_TRACK(board)
    t.SetStart(point(a));t.SetEnd(point(b));t.SetWidth(pcb.FromMM(width))
    t.SetLayer(layer);t.SetNetCode(net);board.Add(t)

def via(p,net):
    v=pcb.PCB_VIA(board)
    v.SetPosition(point(p));v.SetWidth(pcb.FromMM(.6));v.SetDrill(pcb.FromMM(.3))
    v.SetViaType(pcb.VIATYPE_THROUGH);v.SetLayerPair(pcb.F_Cu,pcb.B_Cu)
    v.SetNetCode(net);board.Add(v)

def route(start,end,points=(),width=.25,back=False):
    a,b=pad(*start),pad(*end)
    assert a.GetNetCode() and a.GetNetCode()==b.GetNetCode(),(start,end)
    nodes=[pos(a),*points,pos(b)]
    # Back-layer branches use vias at the specified escape points for SMD pads.
    # Through-hole pads already join both layers.
    layer=pcb.B_Cu if back else pcb.F_Cu
    if back:
        # Conventional drilled vias outside paste pads: no via-in-pad process.
        if a.GetAttribute()==pcb.PAD_ATTRIB_SMD:
            escape=(nodes[0][0]+.3625,nodes[0][1]+1.5) if start==('Q4',3) else (nodes[0][0]+1.25,nodes[0][1])
            track(nodes[0],escape,a.GetNetCode(),pcb.F_Cu,width)
            via(escape,a.GetNetCode());nodes[0]=escape
        if b.GetAttribute()==pcb.PAD_ATTRIB_SMD:
            escape=(nodes[-1][0]-1.1,nodes[-1][1])
            track(escape,nodes[-1],a.GetNetCode(),pcb.F_Cu,width)
            via(escape,a.GetNetCode());nodes[-1]=escape
    for first,second in zip(nodes,nodes[1:]):track(first,second,a.GetNetCode(),layer,width)
    report.append(dict(net=a.GetNetname(),start=list(start),end=list(end),points_mm=nodes,
        layer='B.Cu' if back else 'F.Cu',width_mm=width,
        length_mm=sum(math.dist(x,y) for x,y in zip(nodes,nodes[1:]))))

# ADC filter and MOS gating: short local branches, no long trace at ADC node.
route(('R17',2),('R18',1),[(98.55,29),(98.55,31.3),(96.175,33)])
route(('R18',1),('C28',1),[(96.175,36.95)])
route(('R18',2),('C28',2),[(97.825,36.95)])
route(('Q3',3),('R17',1),[(95.7,18),(96.175,18.475)])
route(('Q3',1),('R15',2),[(93.0625,15.0)])
route(('Q3',2),('R15',1),[(91.2,18.95),(91.2,14.975)])
route(('Q4',3),('Q3',1),[(96.0,24),(96.0,20.0),(93.0625,17.05)],back=True)
route(('R16',1),('Q4',1),[(88.175,22.0),(92.0125,22.0)])
route(('R19',2),('R20',1),[(95.65,44),(95.65,46.0),(93.175,48)])
route(('R20',1),('C29',1),[(93.175,51.95)])
route(('C29',1),('Q5',1),[(93.0625,52.1625)])
route(('R20',2),('C29',2),[(94.825,51.95)])
route(('Q5',3),('R21',2),[(96.1,56),(96.1,59.725)])

# Call button and reset local branches. THT switch duplicated pad numbers are
# connected internally by the purchased switch, not by assumed copper shorts.
route(('R14',2),('C27',1),[(55.225,55.6)])
route(('C27',1),('J17',1),[(55.0,56.225)])
route(('J17',1),('SW1',1),[(55.0,62.0),(52.0,65.0)])
route(('C27',2),('J17',2),[(58.6,55),(58.6,58.94)])
route(('J17',2),('SW1',2),[(60.8,60),(60.8,71.0),(53.5,71.0)])
route(('R25',2),('C30',1))
route(('SW2',1),('R25',2),[(70.0,67.0),(72.825,67.0)])

# Dedicated flash debug test pads to TTL header. Back traces do not cross any
# USB/RF pair, and make no signal-integrity claim for the future USB harness.
route(('TP4',1),('J18',2),[(37.0,42.0),(37.0,65.46)],back=True)
route(('TP5',1),('J18',3),[(38.5,44.5),(38.5,64.42)],back=True)
route(('TP6',1),('J18',1),[(60.8,47.0),(60.8,72.0),(41.0,72.0)],back=True)

pcb.SaveBoard(str(boardfile),board)
(ROOT/'exports/routing-review.json').write_text(json.dumps({
    'status':'PARTIAL_ROUTING_NOT_FOR_FABRICATION','branches':report,
    'track_segments':len(list(board.GetTracks())),'power_routed':False,
    'rf_routed':False,'usb_routed':False,'ground_planes_complete':False,
    'manufacturing_ready':False,'drc_result':'See placement-drc.json after CLI run'
},indent=2)+'\n',encoding='utf-8')
print('Routed local branches:',len(report),'copper items:',len(list(board.GetTracks())))
