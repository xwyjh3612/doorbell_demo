"""Plan a bent pad neck to a clear off-pad via using actual obstacles.

Straight radial escapes can fail even when a short bent route is feasible.
This tool keeps every pad and net, and requires independent native DRC.
"""
import datetime
import json
import math
import os
import shutil
import subprocess

from comparison_route_geometry import b, FILE, p, pos, route, layers
from local_escape_review import pad, obstruction

ref, number = os.environ['A18_ESCAPE_PAD'].split('.')
d = pad(ref, number)
net = d.GetNetname()
start = pos(d)
layer = d.GetParentFootprint().GetLayer()
diameter = float(os.environ.get('A18_NECK_VIA_DIAMETER', '.45'))
drill = float(os.environ.get('A18_NECK_VIA_DRILL', '.2'))
width = float(os.environ.get('A18_NECK_WIDTH', '.25'))
assert diameter >= drill+.2
radius = float(os.environ.get('A18_NECK_SEARCH_RADIUS', '4'))
explicit = json.loads(os.environ.get('A18_NECK_VIA_POINTS', '[]'))
points = explicit or [(start[0]+dx*.2,start[1]+dy*.2)
                      for dx in range(-20,21) for dy in range(-20,21)
                      if .8 <= math.hypot(dx*.2,dy*.2) <= radius]
clear = [q for q in points if not obstruction(net,q,q,layer,diameter,width,drill)]
if os.environ.get('A18_NECK_REACH_MAP'):
    import numpy as np
    with np.load(os.environ['A18_NECK_REACH_MAP']) as saved:
        field={k:saved[k]for k in ('xs','ys','reachable')}
    def in_reachable_area(xy):
        ix=round((xy[0]-field['xs'][0])/(field['xs'][1]-field['xs'][0]));iy=round((xy[1]-field['ys'][0])/(field['ys'][1]-field['ys'][0]))
        if not(0<=ix<len(field['xs'])and 0<=iy<len(field['ys'])):return False
        return bool(field['reachable'][:,iy,ix].any())
    clear=[q for q in clear if in_reachable_area(q)]
clear.sort(key=lambda q:math.dist(start,q))
log = []
success = False
snapshot = FILE.parent/'iterations'/('before-bent-neck-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE,snapshot/FILE.name)
os.environ['A18_ROUTE_VIA_DIAMETER_MM'] = str(diameter)
os.environ['A18_ROUTE_VIA_DRILL_MM'] = str(drill)
trial_limit = int(os.environ.get('A18_NECK_TRIAL_LIMIT', '30'))
cli = FILE.parents[3]/'build/cad-tools/kicad/bin/kicad-cli.exe'
os.environ['A18_ROUTE_RIPUP_SIGNAL_WIRES']='0'
for xy in clear[:trial_limit]:
    existing={t.m_Uuid.AsString() for t in b.GetTracks()}
    bounds=(max(.5,start[0]-radius-.5),max(.5,start[1]-radius-.5),
            min(72.5,start[0]+radius+.5),min(72.5,start[1]+radius+.5))
    try:
        entry=route(net,start,xy,{layers.index(layer)},{layers.index(layer)},width=width,
                    step=float(os.environ.get('A18_NECK_GRID_MM','.05')),bounds=bounds)
    except RuntimeError as error:
        log.append({'via_mm':xy,'success':False,'error':str(error)})
        continue
    # The search may already place a layer transition at the goal anchor.
    # Reuse that physical via instead of adding a second coincident drill.
    v=next((t for t in b.GetTracks() if isinstance(t,p.PCB_VIA)
            and t.GetNetname()==net and math.dist(pos(t),xy)<.00001),None)
    # A bent route may already transition just before the final goal anchor.
    # Its last segment joins that via to the goal. Reuse this newly created
    # physical escape instead of drilling a second hole within the minimum
    # drill spacing. Native connectivity/clearance still accepts the result.
    if v is None:
        nearby=[t for t in b.GetTracks() if isinstance(t,p.PCB_VIA)
                and t.m_Uuid.AsString() not in existing and t.GetNetname()==net
                and math.dist(pos(t),xy)<drill+.255]
        if nearby:v=min(nearby,key=lambda t:math.dist(pos(t),xy))
    if v is None:
        v=p.PCB_VIA(b)
        v.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
        v.SetWidth(p.FromMM(diameter));v.SetDrill(p.FromMM(drill))
        v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu)
        v.SetNetCode(d.GetNetCode());b.Add(v)
    v.SetLocked(True)
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    native_file=FILE.parent/'exports'/('neck-native-'+ref+'-'+number+'.json')
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(native_file),str(FILE)],check=True,capture_output=True)
    native=json.loads(native_file.read_text(encoding='utf-8'))
    hard=[q for q in native['violations'] if q['type'] not in ['track_dangling','via_dangling']]
    if hard:
        held=[]
        for t in list(b.GetTracks()):
            if t.m_Uuid.AsString() not in existing:
                b.Remove(t);held.append(t)
        b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
        for t in held:t.thisown=False
        log.append({'via_mm':xy,'success':False,'native_hard_findings':hard})
        continue
    log.append({'via_mm':xy,'success':True,**entry})
    success=True
    break
report={'pad':ref+'.'+number,'net':net,'neck_width_mm':width,
        'via_diameter_mm':diameter,'via_drill_mm':drill,'trials':log,
        'success':success,'native_DRC_checked':True,'native_DRC_required':True}
(FILE.parent/'exports'/('bent-neck-'+ref+'-'+number+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
