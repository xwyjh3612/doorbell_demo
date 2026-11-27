"""Try a small regulator shift and local microphone jog on an isolated board.

Original pad identities and net assignments are retained. Native DRC is the
decision criterion; this does not publish into the accepted board.
"""
import itertools
import json
import os
from pathlib import Path
import subprocess

import pcbnew as p

root = Path(__file__).resolve().parents[2]
target = Path(os.environ['A18_REPAIR_BOARD']).resolve()
source = Path(os.environ['A18_UART_CANDIDATE']).resolve()
assert target != source and target.is_relative_to(root/'hardware')
cli = root/'build/cad-tools/kicad/bin/kicad-cli.exe'
out = target.parent/'exports'
out.mkdir(exist_ok=True)
log = []
settings = p.GetSettingsManager()
settings.LoadProject(str(target.with_suffix('.kicad_pro')))

def xy(q):
    return p.ToMM(q.x), p.ToMM(q.y)

def vec(q):
    return p.VECTOR2I(p.FromMM(q[0]), p.FromMM(q[1]))

def add_track(b, net, a, z, width, layer):
    t = p.PCB_TRACK(b)
    t.SetStart(vec(a)); t.SetEnd(vec(z))
    t.SetWidth(width); t.SetLayer(layer)
    t.SetNetCode(b.FindNet(net).GetNetCode()); b.Add(t)

# The jog spans only the regulator pad, preserving microphone route endpoints.
for dx, jog in itertools.product((-.09, -.095, -.1, -.105, -.11), (.01, .02, .03, .04)):
    b = p.LoadBoard(str(source))
    b.SetProject(settings.GetProject(str(target.with_suffix('.kicad_pro'))))
    b.SynchronizeNetsAndNetClasses(False)
    f = next(f for f in b.GetFootprints() if f.GetReference() == 'U19')
    f.SetPosition(vec((17+dx,38)))
    removed = []
    for t in list(b.GetTracks()):
        if isinstance(t,p.PCB_VIA) or t.GetNetname()!='I2S_MIC_DATA12' or t.GetLayer()!=p.B_Cu:
            continue
        a,z=xy(t.GetStart()),xy(t.GetEnd())
        if abs(a[0]-15)<.00001 and abs(z[0]-15)<.00001 and min(a[1],z[1])<39.2:
            removed.append(t);b.Remove(t)
            points=[a,(15,40.6),(15-jog,40.6-jog),(15-jog,39.1263)]
        elif abs(a[0]-15)<.00001 and abs(a[1]-39.1263)<.00001 and abs(z[0]-13.4291)<.00001:
            removed.append(t);b.Remove(t)
            points=[(15-jog,39.1263),z]
        else:
            continue
        for s,e in zip(points,points[1:]):
            add_track(b,t.GetNetname(),s,e,t.GetWidth(),t.GetLayer())
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(target),b)
    reportfile=out/'uart-local-native.json'
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(reportfile),str(target)],check=True,capture_output=True)
    report=json.loads(reportfile.read_text(encoding='utf-8'))
    hard=[v for v in report['violations'] if v['type'] not in ('track_dangling','via_dangling')]
    record={'dx':dx,'jog':jog,'unconnected':len(report['unconnected_items']),'hard':hard,'findings':len(report['violations'])}
    log.append(record)
    (out/'uart-local-search.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k!='hard'}),flush=True)
    for t in removed:t.thisown=False
    if not hard:
        designfile=target.parent/'design.json'
        design=json.loads(designfile.read_text(encoding='utf-8'))
        for q in design['parts']:
            if q['ref']=='U19':q.update(x=17+dx,y=38)
        designfile.write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
        break
else:
    raise RuntimeError('No native-clear local candidate; target is a rejected trial')
