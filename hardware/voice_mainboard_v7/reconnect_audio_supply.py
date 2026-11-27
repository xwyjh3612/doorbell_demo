"""Connect the local audio supply to the saved main power network."""
import sys,types,json,subprocess,hashlib
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
FILE=ROOT/'voice_mainboard_v7.kicad_pcb'
source=(ROOT.parent/'voice_mainboard_v3/route_helpers.py').read_text(encoding='utf-8')
source=source.replace('    obstacle=unary_union(obstacles)', '''    for zone in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not zone.GetIsRuleArea() or not zone.IsOnLayer(layer):continue
        for zi in range(zone.Outline().OutlineCount()):
            ring=zone.Outline().COutline(zi)
            obstacles.append(Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]).buffer(width/2+.005))
    obstacle=unary_union(obstacles)''')
source=source.replace('    blocked=unary_union(all_obstacles);fblocked=unary_union(front)', '''    for zone in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not zone.GetIsRuleArea():continue
        for zi in range(zone.Outline().OutlineCount()):
            ring=zone.Outline().COutline(zi)
            sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
            all_obstacles.append(sh.buffer(diameter/2+.005))
            if zone.IsOnLayer(layer):front.append(sh.buffer(neck/2+.005))
    blocked=unary_union(all_obstacles);fblocked=unary_union(front)''')
sys.argv=[__file__,str(FILE)]
r=types.ModuleType('v7_supply_router');exec(compile(source,'v7_supply_router','exec'),r.__dict__)
b=r.board
r.escapevia('audio_supply',('U14',8),diameter=.8,drill=.4,neck=.25)
r.virtual['main_supply']=next(t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.GetNetname()=='SYS_5V'and abs(p.ToMM(t.GetPosition().x)-58.8)<.01)
multi=(ROOT.parent/'voice_mainboard_v3/route_multilayer.py').read_text(encoding='utf-8')
multi=multi.replace('layers=[p.F_Cu,p.B_Cu,p.In2_Cu]','layers=[p.F_Cu,p.B_Cu]').replace('range(3)','range(len(layers))')
multi=multi.replace('from shapely.geometry import Point,LineString','from shapely.geometry import Point,LineString,Polygon')
multi=multi.replace('        shapes=[]','''        shapes=[]
        for zone in [*b.Zones(), *[z for fp in b.GetFootprints() for z in fp.Zones()]]:
            if not zone.GetIsRuleArea() or not zone.IsOnLayer(layer):continue
            for zi in range(zone.Outline().OutlineCount()):
                ring=zone.Outline().COutline(zi)
                sh=Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())])
                shapes.append(sh.buffer(clearance));via_obstacles.append(sh.buffer(.505))''')
# A reached pad must use the actual pad layer.
r.virtual['audio_supply'].IsOnLayer=lambda layer:layer in [p.F_Cu,p.B_Cu]
m=types.ModuleType('v7_multilayer');exec(compile(multi,'v7_multilayer','exec'),m.__dict__)
results=[]
try:
    r.route(('audio_supply',0),('main_supply',0),layer=p.B_Cu,width=.5,step=.1,bounds=(50,1,98,35))
    results.append({'main_audio_supply':True,'routing':'B.Cu','width_mm':.5})
except (RuntimeError,AssertionError):
    results.append({'main_audio_supply':True,'routing':m.route(r,('audio_supply',0),('main_supply',0),width=.5,step=.1,bounds=(45,1,98,45))})
try:
    r.route(('R31',1),('C61',1),width=.25,step=.05,bounds=(82,19,92,29))
    results.append({'R31_supply':True})
except (RuntimeError,AssertionError):
    results.append({'R31_supply':m.route(r,('R31',1),('C61',1),width=.25,step=.1,bounds=(82,18,96,32))})
for f in b.GetFootprints():
    if f.GetReference()=='U14':f.Reference().SetVisible(False)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
CLI=ROOT.parents[1]/'build/cad-tools/kicad/bin/kicad-cli.exe'
subprocess.run([str(CLI),'pcb','drc','--schematic-parity','--severity-all','--format','json','-o',str(ROOT/'exports/drc.json'),str(FILE)],check=True)
d=json.loads((ROOT/'exports/drc.json').read_text(encoding='utf-8'))
report=json.loads((ROOT/'exports/local-layout-validation.json').read_text(encoding='utf-8'))
report.update(PCB_sha256=hashlib.sha256(FILE.read_bytes()).hexdigest(),DRC_errors=sum(v['severity']=='error'for v in d['violations']),
              DRC_warnings=sum(v['severity']=='warning'for v in d['violations']),unconnected=len(d['unconnected_items']),schematic_parity=len(d['schematic_parity']),main_supply_reconnect=results)
(ROOT/'exports/local-layout-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items()if k not in ['removed_stubs']},ensure_ascii=False,indent=2))
