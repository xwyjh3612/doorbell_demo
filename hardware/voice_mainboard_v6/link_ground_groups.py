"""Join the independent polygon graph's remaining physical ground groups."""
from pathlib import Path
import json,math
import remove_floating_ground as graph
from two_layer_support import load
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
r,m=load();p=r.p;anchor=r.pad('TP6',1);main=graph.root(graph.locate(r.pos(anchor),p.F_Cu));report=[]
groups={graph.root(i) for i in graph.anchored if graph.root(i)!=main}
for group in groups:
    candidates=[]
    for t in r.board.GetTracks():
        if not isinstance(t,p.PCB_VIA) or t.GetNetname()!='GND':continue
        i=graph.locate(r.pos(t),p.F_Cu)
        if i is not None and graph.root(i)==group:candidates.append(t)
    candidates.sort(key=lambda t:math.dist(r.pos(t),r.pos(anchor)))
    name='actual_ground_group_'+str(group)
    if not candidates:
        pads=[]
        for f in r.board.GetFootprints():
            for pd in f.Pads():
                if pd.GetNetname()!='GND':continue
                i=graph.locate(r.pos(pd),p.F_Cu)
                if i is not None and graph.root(i)==group:pads.append((f.GetReference(),pd.GetNumber()))
        pads.sort(key=lambda pair:math.dist(r.pos(r.pad(*pair)),r.pos(anchor)))
        escaped=False
        for pair in pads:
            try:r.escapevia(name,pair,diameter=.6,drill=.3,neck=.2);escaped=True;break
            except (RuntimeError,AssertionError):pass
        if not escaped:
            r.virtual[name]=r.pad(*pads[0])
    else:r.virtual[name]=candidates[0]
    try:m.route(r,(name,0),('TP6',1),width=.25,step=.1,bounds=(.6,.6,99.4,74.4));report.append({'group':group,'connected':True})
    except (RuntimeError,AssertionError) as e:report.append({'group':group,'connected':False,'reason':str(e)})
    p.SaveBoard(str(FILE),r.board)
r.board.BuildConnectivity();assert p.ZONE_FILLER(r.board).Fill(r.board.Zones());p.SaveBoard(str(FILE),r.board)
(ROOT/'exports/ground-group-links.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(report)
