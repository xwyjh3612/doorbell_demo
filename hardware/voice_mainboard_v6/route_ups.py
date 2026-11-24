"""Iterative native-DRC-driven routing. Never suppress or waive violations."""
from pathlib import Path
import json, subprocess, math, sys
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
FILE=ROOT/'voice_mainboard_v6.kicad_pcb'
CLI=ROOT.parents[1]/'build/cad-tools/kicad/bin/kicad-cli.exe'
REPORT=ROOT/'exports/routed-drc.json'
history=[]
def check():
    subprocess.run([str(CLI),'pcb','drc','--format','json','-o',str(REPORT),str(FILE)],check=True,capture_output=True)
    return json.loads(REPORT.read_text(encoding='utf8'))
def fill(b):
    for z in b.Zones():
        if not z.GetIsRuleArea():
            z.SetPadConnection(p.ZONE_CONNECTION_FULL)
            z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
def zone(b):
    if any(not z.GetIsRuleArea() for z in b.Zones()):return
    for layer in [p.F_Cu,p.B_Cu]:
        z=p.ZONE(b);z.SetLayer(layer);z.SetNet(b.FindNet('GND'));z.SetLocalClearance(p.FromMM(.2));z.SetPadConnection(p.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(p.FromMM(.25));z.SetThermalReliefSpokeWidth(p.FromMM(.3));z.SetMinThickness(p.FromMM(.2))
        z.Outline().NewOutline()
        for x,y in [(.5,.5),(99.5,.5),(99.5,74.5),(.5,74.5)]:z.Outline().Append(p.FromMM(x),p.FromMM(y))
        b.Add(z)
    fill(b)
def cleanup(d):
    b=p.LoadBoard(str(FILE));held=[]
    ids={i['uuid'] for v in d['violations'] if v['type'] in ['shorting_items','clearance','hole_clearance','track_dangling','via_dangling','solder_mask_bridge'] for i in v['items']}
    for t in list(b.GetTracks()):
        if t.m_Uuid.AsString() in ids:held.append(t);b.Remove(t)
    # New footprints take precedence over inherited silk labels, not copper clearance.
    silkids={i['uuid'] for v in d['violations'] if v['type']=='silk_over_copper' for i in v['items']}
    for f in b.GetFootprints():
        if f.Reference().m_Uuid.AsString() in silkids:f.Reference().SetVisible(False)
    for item in list(b.GetDrawings()):
        if item.m_Uuid.AsString() in silkids and isinstance(item,p.PCB_TEXT):held.append(item);b.Remove(item)
    fill(b)
    for t in held:t.thisown=False
    return len(held)
def endpoint(r,item,key):
    uid=item['uuid']
    for f in r.board.GetFootprints():
        for pad in f.Pads():
            if pad.m_Uuid.AsString()==uid:r.virtual[key]=pad;return key,0
    for t in r.board.GetTracks():
        if t.m_Uuid.AsString()!=uid:continue
        pos=item['pos'];target=(pos['x'],pos['y'])
        if isinstance(t,p.PCB_VIA):r.virtual[key]=t
        else:
            pts=[(p.ToMM(pt.x),p.ToMM(pt.y)) for pt in [t.GetStart(),t.GetEnd()]]
            pt=min(pts,key=lambda pt:math.dist(pt,target));ep=r.Endpoint(t.GetNetname(),pt);ep.IsOnLayer=lambda layer,la=t.GetLayer():layer==la;r.virtual[key]=ep
        return key,0
    raise RuntimeError('Unknown DRC endpoint '+uid)

d=check()
for _ in range(6):
    if not cleanup(d):break
    d=check()
r,m=load();zone(r.board)
# Route compact converter loops before generic remaining connections.
pairs=[(('U2',3),('L1',1),.4),(('U2',4),('C4',1),.35),(('U2',1),('C4',1),.25),
       (('U2',5),('R2',2),.2),(('R2',2),('R3',1),.2),(('R2',2),('C37',2),.2),
       (('U15',3),('L4',2),.5),(('U15',4),('L4',1),.5),
       (('U15',7),('C65',1),.4),(('U15',7),('C66',1),.4),
       (('U15',5),('R61',2),.2),(('R61',2),('R62',1),.2),(('U15',6),('R63',1),.2)]
if any(t.GetNetname() == 'UPS_SW' for t in r.board.GetTracks()):
    pairs = []  # Resume after local copper has already been saved.
for a,z,w in pairs:
    try:
        r.route(a,z,width=w,step=.05,bounds=(.6,.6,99.4,74.4))
        history.append({'from':a,'to':z,'width':w,'routed':True,'method':'local_loop'})
    except (RuntimeError, AssertionError) as e:history.append({'from':a,'to':z,'routed':False,'reason':str(e)})
    p.SaveBoard(str(FILE),r.board)
fill(r.board)
for iteration in range(12):
    d=check();cleanup(d);d=check()
    print('Pass',iteration,'DRC',len(d['violations']),'open',len(d['unconnected_items']),flush=True)
    if not d['unconnected_items']:break
    r,m=load();progress=0
    # Native zone endpoints are not points at the reported outline origin.
    # Give every reported isolated ground pad an ordinary off-pad via to B.Cu.
    for f in r.board.GetFootprints():
        for pad in f.Pads():
            if pad.GetNetname() != 'GND':continue
            if not any(pad.m_Uuid.AsString() == i['uuid'] for v in d['unconnected_items'] for i in v['items']):continue
            name='ground_'+pad.m_Uuid.AsString();r.virtual[name]=pad
            try:r.escapevia('escape_'+name,(name,0),diameter=.6,drill=.3,neck=.25);progress+=1
            except (RuntimeError,AssertionError):pass
    power_names=['SYS_5V','BAT_SENSE_IN','BAT_BOOST_5V','VIN_PROTECTED','CELL_NEG','GND']
    remaining=sorted(d['unconnected_items'],key=lambda v:any('['+n+']' in i['description'] for n in power_names for i in v['items']))
    for index,v in enumerate(remaining):
        if len(v['items'])<2:continue
        try:a=endpoint(r,v['items'][0],'A'+str(index));z=endpoint(r,v['items'][1],'Z'+str(index))
        except RuntimeError:continue  # Ground planes are joined by real copper/vias above.
        n=r.pad(*a).GetNetname()
        if n!=r.pad(*z).GetNetname():raise RuntimeError('DRC endpoint net mismatch')
        aa,zz=r.pos(r.pad(*a)),r.pos(r.pad(*z))
        bounds=(max(.6,min(aa[0],zz[0])-5),max(.6,min(aa[1],zz[1])-5),min(99.4,max(aa[0],zz[0])+5),min(74.4,max(aa[1],zz[1])+5))
        w=.25 if n in ['SYS_5V','BAT_SENSE_IN','BAT_BOOST_5V','VIN_PROTECTED','CELL_NEG'] else .2
        try:
            try:
                if not (r.pad(*a).IsOnLayer(p.F_Cu) and r.pad(*z).IsOnLayer(p.F_Cu)):raise RuntimeError('Layer transition required')
                r.route(a,z,width=w,step=.1,bounds=bounds)
            except (RuntimeError, AssertionError):
                try:m.route(r,a,z,width=w,step=.1,bounds=bounds)
                except RuntimeError:
                    wider=(max(.6,bounds[0]-5),max(.6,bounds[1]-5),min(99.4,bounds[2]+5),min(74.4,bounds[3]+5))
                    m.route(r,a,z,width=w,step=.1,bounds=wider)
            progress+=1;history.append({'net':n,'routed':True,'width_mm':w,'iteration':iteration})
        except (RuntimeError,AssertionError) as e:
            history.append({'net':n,'routed':False,'iteration':iteration,'reason':str(e)})
        if index%8==0:p.SaveBoard(str(FILE),r.board)
    fill(r.board)
    (ROOT/'exports/routing-history.json').write_text(json.dumps(history,indent=2)+'\n',encoding='utf8')
    if not progress:break
d=check();print('Final',len(d['violations']),len(d['unconnected_items']),flush=True)
