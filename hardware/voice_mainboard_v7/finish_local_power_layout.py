"""Reconnect supply trunks after local decoupling relocation and audit V7."""
import hashlib,json,subprocess,sys,types,math
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
FILE=ROOT/'voice_mainboard_v7.kicad_pcb'
CLI=REPO/'build/cad-tools/kicad/bin/kicad-cli.exe'
source=(ROOT.parent/'voice_mainboard_v3/route_helpers.py').read_text(encoding='utf-8')
source=source.replace('    obstacle=unary_union(obstacles)', '''    for z in [*board.Zones(), *[z for fp in board.GetFootprints() for z in fp.Zones()]]:
        if not z.GetIsRuleArea() or not z.IsOnLayer(layer):continue
        for i in range(z.Outline().OutlineCount()):
            ring=z.Outline().COutline(i)
            obstacles.append(Polygon([(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]).buffer(width/2+.005))
    obstacle=unary_union(obstacles)''')
sys.argv=[__file__,str(FILE)]
r=types.ModuleType('v7_finish_router');exec(compile(source,'v7_finish_router','exec'),r.__dict__)
b=r.board
def endpoint(key,net,x,y):
    r.virtual[key]=r.Endpoint(net,(x,y));return key,0
result=[]
pairs=[(endpoint('sys_local','SYS_5V',92.5,21.2),endpoint('sys_backbone','SYS_5V',85,24.6),p.B_Cu,.5,(80,14,98,28)),
       (('U14',8),('R75',1),p.F_Cu,.25,(85,12,98,25)),
       (('C68',1),endpoint('battery_backbone','BAT_SENSE_IN',40.65,62.4),p.F_Cu,.3,(36,54,48,67))]
for a,z,layer,width,bounds in pairs:
    try:
        r.route(a,z,layer=layer,width=width,step=.05,bounds=bounds)
        result.append({'from':a,'to':z,'layer':b.GetLayerName(layer),'width_mm':width,'routed':True})
    except (RuntimeError,AssertionError) as e:
        result.append({'from':a,'to':z,'routed':False,'error':str(e)})
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
def check():
    subprocess.run([str(CLI),'pcb','drc','--schematic-parity','--severity-all','--format','json','-o',str(ROOT/'exports/drc.json'),str(FILE)],check=True,capture_output=True)
    return json.loads((ROOT/'exports/drc.json').read_text(encoding='utf-8'))
d=check();removed=[]
for _ in range(12):
    b=p.LoadBoard(str(FILE));held=[]
    stubs={i['uuid']for v in d['violations']if v['type']in ['track_dangling','via_dangling']for i in v['items']}
    for t in list(b.GetTracks()):
        if t.m_Uuid.AsString() in stubs:
            removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'reason':'Native DRC dangling after former capacitor move'})
            held.append(t);b.Remove(t)
    # References are relocated for silk legibility, never copper constraints.
    for f in b.GetFootprints():
        if f.GetReference() in ['C61','C62','C67','C68']:f.Reference().SetVisible(False)
        if f.GetReference()=='U14':
            f.Reference().SetPosition(p.VECTOR2I(p.FromMM(89.3),p.FromMM(17.3)))
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    for t in held:t.thisown=False
    d=check()
    if not stubs:break

measurement={}
for ref,target in [('C62',('U14',7)),('C61',('U14',8)),('C67',('U16',4)),('C68',('U16',5))]:
    fa=next(f for f in b.GetFootprints()if f.GetReference()==ref)
    ft=next(f for f in b.GetFootprints()if f.GetReference()==target[0])
    aa=next(a for a in fa.Pads()if a.GetNumber()=='1');zz=next(z for z in ft.Pads()if z.GetNumber()==str(target[1]))
    dist=math.hypot(p.ToMM(aa.GetPosition().x-zz.GetPosition().x),p.ToMM(aa.GetPosition().y-zz.GetPosition().y))
    measurement[ref]={'target':list(target),'distance_mm':dist,'scope':'Straight-line pad center distance, not routed loop length'}
report={'date':'2026-11-24','PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'DRC_errors':sum(v['severity']=='error'for v in d['violations']),
        'DRC_warnings':sum(v['severity']=='warning'for v in d['violations']),'unconnected':len(d['unconnected_items']),
        'schematic_parity':len(d['schematic_parity']),'supply_routes':result,'removed_stubs':removed,'pad_distances':measurement,
        'manufacturing_ready':False,'full_board_relayout_completed':False,'2A_qualified':False}
(ROOT/'exports/local-layout-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
