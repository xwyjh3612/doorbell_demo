"""Complete power connections with narrow package exits and wide inner trunks.

Do not route any signal on In1; it remains the continuous reference ground.
Validate with KiCad DRC and inspect current-carrying traces separately.
"""
from pathlib import Path
import sys,json
import pcbnew as p
import math
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
b=r.board;report=[];escapes={}
progressfile=root/'exports/power-trunks.json'
if progressfile.exists():
    saved=json.loads(progressfile.read_text(encoding='utf8'));report=saved['branches']
    for key,value in saved.get('escape_vias',{}).items():
        ref,pin=key.split('/');name='v_'+ref+'_'+pin;pair=(ref,int(pin))
        r.virtual[name]=r.Endpoint(value['net'],value['position_mm']);escapes[pair]=(name,0)
fanout=root/'exports/mux-fanout.json'
if fanout.exists():
    for item in json.loads(fanout.read_text(encoding='utf8'))['pins']:
        pair=('U10',item['pin']);name='v_U10_'+str(item['pin'])
        r.virtual[name]=r.Endpoint(item['net'],item['via_mm']);escapes[pair]=(name,0)
def endpoint(pair,neck=.2):
    pd=r.pad(*pair)
    if pd.GetAttribute()==p.PAD_ATTRIB_PTH:return pair
    if pair not in escapes:
        name='v_'+pair[0]+'_'+str(pair[1])
        try:r.escapevia(name,pair,neck=neck)
        except RuntimeError:
            print('Route directly from SMT pad before a farther layer change:',pair,flush=True);return pair
        escapes[pair]=(name,0)
    return escapes[pair]
def link(a,z,width=.25,neck=.2):
    if any(tuple(x['from'])==a and tuple(x['to'])==z for x in report):return
    aa,zz=endpoint(a,neck),endpoint(z,neck)
    if width>=.5:
        from shapely.geometry import Point,LineString
        from shapely.ops import unary_union
        def widen(pair):
            pd=r.pad(*pair);net=pd.GetNetname();xy=r.pos(pd)
            if hasattr(pd,'IsOnLayer')and not pd.IsOnLayer(p.In2_Cu):return pair
            shapes=[]
            for fp in b.GetFootprints():
                for pp in fp.Pads():
                    if pp.GetNetname()!=net and pp.IsOnLayer(p.In2_Cu):shapes.extend(sh.buffer(width/2+.205)for sh in r.polygons(pp,p.In2_Cu))
            for t in b.GetTracks():
                if t.GetNetname()==net:continue
                if isinstance(t,p.PCB_VIA):shapes.append(Point(r.pos(t)).buffer(p.ToMM(t.GetWidth(p.F_Cu))/2+width/2+.205))
                elif t.GetLayer()==p.In2_Cu:shapes.append(LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))]).buffer(p.ToMM(t.GetWidth())/2+width/2+.205))
            blocked=unary_union(shapes)
            if not blocked.intersects(Point(xy)):return pair
            name='taper_'+pair[0]+'_'+str(pair[1])
            candidates=[(xy[0]+dx*.2,xy[1]+dy*.2)for dx in range(-15,16)for dy in range(-15,16)]
            for pt in sorted(candidates,key=lambda pt:math.dist(xy,pt)):
                if math.dist(xy,pt)<2.8 or blocked.intersects(Point(pt)):continue
                r.virtual[name]=r.Endpoint(net,pt)
                try:r.route(pair,(name,0),layer=p.In2_Cu,width=.25,step=.05,bounds=(xy[0]-4,xy[1]-4,xy[0]+4,xy[1]+4))
                except RuntimeError:continue
                print('Short 0.25mm inner-layer package taper',pair,pt,flush=True)
                return(name,0)
            raise RuntimeError('No safe wide-trunk transition '+str(pair))
        aa,zz=widen(aa),widen(zz)
    src,goal=r.pos(r.pad(*aa)),r.pos(r.pad(*zz))
    bounds=(max(1.6,min(src[0],goal[0])-6),max(1.6,min(src[1],goal[1])-6),min(98.4,max(src[0],goal[0])+6),min(73.4,max(src[1],goal[1])+6))
    routed=False;last_error=None
    for layer,box in [(p.In2_Cu,bounds),(p.In2_Cu,(1.6,1.6,98.4,73.4)),(p.B_Cu,bounds),(p.F_Cu,bounds)]:
        if any(hasattr(pd,'IsOnLayer')and not pd.IsOnLayer(layer)for pd in [r.pad(*aa),r.pad(*zz)]):continue
        try:r.route(aa,zz,layer=layer,width=width,step=.1,bounds=box);routed=True;break
        except RuntimeError as error:last_error=error
    if not routed:
        from route_multilayer import route
        details=route(r,aa,zz,width=width,bounds=(1.6,1.6,98.4,73.4))
    else:details={'layers':[b.GetLayerName(layer)],'new_vias':0}
    report.append({'from':a,'to':z,'width_mm':width,'routing':details,'package_neck_mm':neck})
try:
    # New rated-current jack. Positive is manufacturer pin4.
    if not any(t.GetNetname()=='VIN_DC'for t in b.GetTracks()):
        r.route(('J1',4),('F1',1),width=.8,bounds=(12,10,24,22),step=.05)
    # Mux source and main output are the complete-system current paths.
    link(('U10',3),('JP4',1),.8)
    link(('Q6',2),('JP4',1),.8,.25)
    link(('U8',4),('JP4',1),.4,.3)
    link(('C46',1),('U10',3),.4)
    link(('D5',1),('JP4',1),.2)
    link(('R50',1),('JP4',1),.2)
    # Reserve right-side VIN2/MODE escapes before the output pins; an output
    # via must not block the neighboring 0.5mm-pitch input lead's escape.
    endpoint(('U10',6));endpoint(('U10',5))
    link(('U10',6),('C42',1),.8)
    link(('U10',2),('JP4',3),.8)
    link(('U10',7),('U10',2),.8)
    link(('C53',1),('U10',7),.8,.2)
    link(('C48',1),('C53',1),.8,.3)
    # Battery sense/control branches carry micro/milliamps, independent of
    # the wide direct battery-to-inductor copper completed earlier.
    link(('D5',2),('J2',1),.25)
    link(('R45',1),('D5',2),.25)
    link(('R15',1),('J2',1),.25)
    # Restore moved system/ESP32 5V connectors to the regulated rail.
    link(('J15',1),('JP1',2),.8)
    link(('JP3',1),('J15',1),.8)
    link(('TP9',1),('J15',1),.25)
    # Bias MODE on both power sources. U10's MODE is not tied to disappearing
    # VIN1, so battery-mode operation retains comparator-based selection.
    link(('D5',3),('R42',1),.2)
    link(('D5',3),('C50',1),.2)
    link(('C50',1),('U11',8),.2)
    link(('U11',8),('U10',5),.2)
    link(('R53',1),('U10',5),.2)
finally:
    for z in b.Zones():z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    vias={ref+'/'+str(pin):{'net':r.pad(*end).GetNetname(),'position_mm':r.pos(r.pad(*end))}for(ref,pin),end in escapes.items()}
    progressfile.write_text(json.dumps({'branches':report,'escape_vias':vias,'complete':len(report)==22,'hardware_tested':False},indent=2)+'\n',encoding='utf8')
