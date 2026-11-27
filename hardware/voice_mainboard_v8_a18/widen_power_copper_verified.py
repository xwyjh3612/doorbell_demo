"""Widen clear rail segments with native verification after each net.

Preserve pad/via locations and route shape. Reject each net's changes if they
add native violations or unconnected items. This is not a current rating.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from comparison_route_geometry import b, FILE, p, pos, polys, layers, rules, outline, required_clearance
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

rails = {'VIN_DC','VIN_FUSED','VIN_PROTECTED','SYS_5V','MODEM_3V8',
         'BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','UPS_SW','BUCK_SW','ESP_SW'}
target = float(os.environ.get('A18_POWER_WIDTH_TARGET_MM', '.5'))
assert .5 <= target <= 1.2, 'Use a reviewed rail width without changing project minima'
out = FILE.parent/'exports'
snapshot = FILE.parent/'iterations'/('before-rail-widening-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE,snapshot/FILE.name)
cli = Path(__file__).resolve().parents[2]/'build/cad-tools/kicad/bin/kicad-cli.exe'

def check():
    b.BuildConnectivity(); assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(FILE),b)
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(out/'rail-widening-drc.json'),str(FILE)],check=True,capture_output=True)
    return json.loads((out/'rail-widening-drc.json').read_text(encoding='utf-8'))

def hard(r):
    return sum(q['type'] not in ['track_dangling','via_dangling'] for q in r['violations'])

report = check()
assert hard(report) == 0
logs = []
for net in sorted(rails):
    changed = []
    masks = {layer:[] for layer in layers}
    for f in b.GetFootprints():
        for d in f.Pads():
            if d.GetNetname() == net:
                continue
            for layer in layers:
                if d.IsOnLayer(layer):
                    masks[layer].extend(sh.buffer(target/2+required_clearance(net,d.GetNetname())) for sh in polys(d,layer))
            if d.GetDrillSize().x:
                sh = Point(pos(d)).buffer(p.ToMM(d.GetDrillSize().x)/2+target/2+.251)
                for layer in layers:
                    masks[layer].append(sh)
    for t in b.GetTracks():
        if t.GetNetname() == net:
            continue
        for layer in layers:
            if not t.IsOnLayer(layer):
                continue
            if isinstance(t,p.PCB_VIA):
                sh = Point(pos(t)).buffer(p.ToMM(t.GetWidth(layer))/2)
                masks[layer].append(Point(pos(t)).buffer(p.ToMM(t.GetDrill())/2+target/2+.251))
            else:
                a,z = t.GetStart(),t.GetEnd()
                # Reserve enough room for future changes to another rail.
                width = max(p.ToMM(t.GetWidth()),target) if t.GetNetname() in rails else p.ToMM(t.GetWidth())
                sh = LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]).buffer(width/2)
            masks[layer].append(sh.buffer(target/2+required_clearance(net,t.GetNetname())))
    for rule,sh in rules:
        for layer in layers:
            if rule.IsOnLayer(layer) and rule.GetDoNotAllowTracks():
                masks[layer].append(sh.buffer(target/2+.011))
    masks = {l:unary_union(shapes) for l,shapes in masks.items()}
    for t in b.GetTracks():
        if isinstance(t,p.PCB_VIA) or t.GetNetname()!=net or p.ToMM(t.GetWidth())>=target-1e-6:
            continue
        a,z=t.GetStart(),t.GetEnd()
        line=LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))])
        if line.length<.25 or not outline.buffer(-target/2-.501).covers(line) or masks[t.GetLayer()].intersects(line):
            continue
        changed.append((t,t.GetWidth()))
        t.SetWidth(p.FromMM(target))
    if not changed:
        continue
    candidate = check()
    accepted = hard(candidate)==0 and len(candidate['unconnected_items'])<=len(report['unconnected_items'])
    logs.append({'net':net,'accepted':accepted,'segments':len(changed),
                 'native_unconnected_before':len(report['unconnected_items']),
                 'native_unconnected_after':len(candidate['unconnected_items']),
                 'native_hard_violations':hard(candidate)})
    if accepted:
        report=candidate
    else:
        for t,width in changed:
            t.SetWidth(width)
        report=check()
    print(net,'widened' if accepted else 'rejected',len(changed),'segments',flush=True)
report=check()
(out/'rail-widening-review.json').write_text(json.dumps({
    'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'nets':logs,
    'target_width_mm':target,'actual_2A_qualified':False,
    'scope':'Kept route shape and pad/via geometry. Accepted each net only with no hard native DRC violations and no increased unconnected count. Does not qualify necks, thermals or peak current.'
},indent=2),encoding='utf-8')
print('Accepted widened segments:',sum(q['segments'] for q in logs if q['accepted']),flush=True)
