"""Route native KiCad-reported gaps without weakening geometric constraints.

Accepts endpoint pads/tracks/vias from a fresh DRC JSON. Uses short front routes
or conventional off-pad vias and bottom routes. Re-run native DRC afterwards.
"""
from pathlib import Path
import json,sys,importlib.util,math
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
report=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'exports/routed-drc.json'
sys.argv=[__file__,str(file)]
spec=importlib.util.spec_from_file_location('r',ROOT.parent/'voice_mainboard_v3/route_helpers.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
d=json.loads(report.read_text(encoding='utf8'))
objects={pd.m_Uuid.AsString():pd for f in r.board.GetFootprints()for pd in f.Pads()}
objects.update({t.m_Uuid.AsString():t for t in r.board.GetTracks()})
results=[]
def endpoint(obj,item,key):
    net=obj.GetNetname()
    if isinstance(obj,p.PAD):
        xy=r.pos(obj);layer=p.F_Cu if obj.IsOnLayer(p.F_Cu)else p.B_Cu
    elif isinstance(obj,p.PCB_VIA):xy=r.pos(obj);layer=p.B_Cu
    else:
        q=item['pos'];xy=(q['x'],q['y']);layer=obj.GetLayer()
        a=obj.GetStart();b=obj.GetEnd()
        pts=[(p.ToMM(v.x),p.ToMM(v.y))for v in [a,b]]
        xy=min(pts,key=lambda pt:math.dist(pt,xy))
    r.virtual[key]=r.Endpoint(net,xy)
    return (key,1),layer
for i,v in enumerate(d['unconnected_items']):
    if len(v['items'])!=2:continue
    one,two=v['items'];a=objects.get(one['uuid']);b=objects.get(two['uuid'])
    if a is None or b is None or a.GetNetname()!=b.GetNetname():continue
    net=a.GetNetname();e1,l1=endpoint(a,one,'GAP'+str(i)+'A');e2,l2=endpoint(b,two,'GAP'+str(i)+'B')
    x1,y1=r.pos(r.pad(*e1));x2,y2=r.pos(r.pad(*e2))
    bounds=(max(.6,min(x1,x2)-5),max(.6,min(y1,y2)-5),min(99.4,max(x1,x2)+5),min(74.4,max(y1,y2)+5))
    if net=='GND':continue
    try:
        if l1==l2:
            try:r.route(e1,e2,layer=l1,width=.2,step=.07,bounds=bounds)
            except RuntimeError:
                if l1!=p.F_Cu:raise
                raise
        else:raise RuntimeError('Need layer transfer')
        results.append({'net':net,'connected':True,'method':'same layer'});continue
    except RuntimeError:pass
    try:
        transfers=[]
        for j,(obj,ep,layer) in enumerate([(a,e1,l1),(b,e2,l2)]):
            key='VIA'+str(i)+str(j)
            if layer==p.B_Cu:transfers.append(ep);continue
            r.escapevia(key,ep,neck=.2,layer=layer);transfers.append((key,1))
        r.route(*transfers,layer=p.B_Cu,width=.2,step=.07,bounds=bounds)
        results.append({'net':net,'connected':True,'method':'off-pad vias / bottom'})
    except RuntimeError as e:
        results.append({'net':net,'connected':False,'reason':str(e)})
        print('Gap remains:',net,str(e),flush=True)
    finally:p.SaveBoard(str(file),r.board)
assert p.ZONE_FILLER(r.board).Fill(r.board.Zones());p.SaveBoard(str(file),r.board)
(ROOT/'exports/gap-routing.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf8')
print('Reported signal gaps routed:',sum(q['connected'] for q in results),'/',len(results),flush=True)
