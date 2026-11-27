"""Reserve complete UART, reset, audio and USB routes in the new placement.

Independent native connectivity/clearance and USB geometry review are still
required. Connectivity alone does not prove differential-pair compliance.
"""
from pathlib import Path
import json, math
import pcbnew as p
from comparison_route_geometry import b, FILE, route, pos, layers
from repair_comparison_groups import groups
fps = {f.GetReference(): f for f in b.GetFootprints()}
def pad(ref, n): return next(d for d in fps[ref].Pads() if d.GetNumber() == str(n))
def endpoint(d):
    for group in groups(d.GetNetname()):
        if d in group:
            vias = [x for x in group if isinstance(x, p.PCB_VIA)]
            if vias: return min(vias, key=lambda x: math.dist(pos(x), pos(d)))
    return d
pairs = [
    (('U1',17),('U3',4)), (('U1',18),('U4',4)), (('U1',19),('U5',4)),
    (('U1',15),('Q2',3)), (('Q2',3),('C19',1)),
    (('U7',7),('U14',1)), (('U7',8),('U14',16)), (('U7',9),('U14',14)),
    (('U1',59),('R26',1)), (('U1',60),('R27',1)),
    (('R26',2),('J12',3)), (('R27',2),('J12',2)),
    (('U7',13),('R29',2)), (('U7',14),('R28',2)),
    (('U7',10),('U3',3)), (('U7',11),('U4',3)), (('U7',4),('U5',3)),
    (('U7',24),('U18',8)), (('U7',25),('U16',7)),
]
entries = []
for a,z in pairs:
    da,dz = pad(*a),pad(*z); net = da.GetNetname()
    assert net == dz.GetNetname(), (a,z)
    entry = {'from':a,'to':z,'net':net}
    if any(da in g and dz in g for g in groups(net)):
        entry['already_connected'] = True
    else:
        ea,ez = endpoint(da),endpoint(dz)
        sl = {i for i,l in enumerate(layers) if ea.IsOnLayer(l)}
        gl = {i for i,l in enumerate(layers) if ez.IsOnLayer(l)}
        try: entry.update(route(net,pos(ea),pos(ez),sl,gl,width=.16),success=True)
        except RuntimeError as error: entry.update(success=False,reason=str(error))
    entries.append(entry)
    p.SaveBoard(str(FILE),b)
    (FILE.parent/'exports/reserved-bus-routes.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
    print(net,a,z,entry.get('success',entry.get('already_connected',False)),entry.get('reason',''),flush=True)
b.BuildConnectivity();p.SaveBoard(str(FILE),b)
