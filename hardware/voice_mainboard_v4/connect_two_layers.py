"""Route remaining native gaps with a two-layer search and checked through vias.

Uses the geometric search implemented in V3, constrained here to F.Cu/B.Cu.
Every new connection remains subject to KiCad DRC. No inner-layer fallback.
"""
from pathlib import Path
import sys,importlib.util,json,math,types
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
sys.argv=[__file__,str(file)]
spec=importlib.util.spec_from_file_location('r',ROOT.parent/'voice_mainboard_v3/route_helpers.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
source=(ROOT.parent/'voice_mainboard_v3/route_multilayer.py').read_text(encoding='utf8')
source=source.replace('layers=[p.F_Cu,p.B_Cu,p.In2_Cu]','layers=[p.F_Cu,p.B_Cu]').replace('range(3)','range(len(layers))')
source=source.replace('from shapely.geometry import Point,LineString','from shapely.geometry import Point,LineString,Polygon')
source=source.replace('        shapes=[]','''        shapes=[]
        for zone in [*b.Zones(),*[z for f in b.GetFootprints()for z in f.Zones()]]:
            if not zone.GetIsRuleArea() or not zone.IsOnLayer(layer):continue
            outline=zone.Outline()
            for zi in range(outline.OutlineCount()):
                ring=outline.COutline(zi)
                pts=[(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]
                if len(pts)>2:
                    sh=Polygon(pts);shapes.append(sh.buffer(clearance));via_obstacles.append(sh.buffer(.505))''')
m=types.ModuleType('two_layer_search');exec(compile(source,'two_layer_search','exec'),m.__dict__)
d=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
objects={t.m_Uuid.AsString():t for t in r.board.GetTracks()}
objects.update({z.m_Uuid.AsString():z for z in r.board.Zones()})
for f in r.board.GetFootprints():
    for pd in f.Pads():objects[pd.m_Uuid.AsString()]=pd
def setup(obj,it,key):
    if isinstance(obj,p.PAD):
        for fp in r.board.GetFootprints():
            if any(pd.m_Uuid==obj.m_Uuid for pd in fp.Pads()):return fp.GetReference(),obj.GetNumber()
    xy=it['pos'];ep=r.Endpoint(obj.GetNetname(),(xy['x'],xy['y']))
    if isinstance(obj,p.PCB_VIA):ep.IsOnLayer=lambda layer:layer in [p.F_Cu,p.B_Cu]
    else:ep.IsOnLayer=lambda layer,used=obj.GetLayer():layer==used
    r.virtual[key]=ep;return key,1
report=[]
for i,v in enumerate(d['unconnected_items']):
    if len(v['items'])!=2:continue
    it1,it2=v['items'];a,b=objects.get(it1['uuid']),objects.get(it2['uuid'])
    if a is None or b is None or a.GetNetname()!=b.GetNetname():continue
    e1,e2=setup(a,it1,'MS'+str(i)),setup(b,it2,'ME'+str(i))
    try:
        x1,y1=r.pos(r.pad(*e1));x2,y2=r.pos(r.pad(*e2))
        bounds=(max(.6,min(x1,x2)-5),max(.6,min(y1,y2)-5),min(99.4,max(x1,x2)+5),min(74.4,max(y1,y2)+5))
        result=m.route(r,e1,e2,width=.2,step=.05 if a.GetNetname()=='GND'else .1,bounds=bounds)
        report.append({'net':a.GetNetname(),'connected':True,**result})
    except RuntimeError as e:
        report.append({'net':a.GetNetname(),'connected':False,'reason':str(e)})
        print(str(e),flush=True)
    finally:p.SaveBoard(str(file),r.board)
assert p.ZONE_FILLER(r.board).Fill(r.board.Zones());p.SaveBoard(str(file),r.board)
(ROOT/'exports/two-layer-gaps.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Two-layer gaps connected:',sum(q['connected']for q in report),'/',len(report))
