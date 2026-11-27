"""Restore the staggered SYS5 fanout while clearing its output capacitor.

This is an explicit local routing iteration, never a production release.
"""
from pathlib import Path
import datetime, json, shutil
import pcbnew as p

OUT = Path(__file__).resolve().parent / 'two_layer_work'
FILE = OUT / 'voice_mainboard_a18_2layer.kicad_pcb'
snap = OUT / 'iterations' / ('before-mux-output-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snap.mkdir(parents=True)
for name in [FILE.name, 'design.json']:
    shutil.copy2(OUT / name, snap / name)
b = p.LoadBoard(str(FILE))
fps = {f.GetReference(): f for f in b.GetFootprints()}
contract = lambda: sorted((f.GetReference(), d.GetNumber(), d.GetNetname()) for f in b.GetFootprints() for d in f.Pads())
before = contract()
f = fps['C73']
points = {(d.GetPosition().x, d.GetPosition().y) for d in f.Pads()}
held, removed = [], []
for t in list(b.GetTracks()):
    incident = any((q.x, q.y) in points for q in [t.GetStart(), t.GetEnd()])
    old_via = isinstance(t, p.PCB_VIA) and t.GetNetname() == 'BAT_BOOST_5V' and abs(p.ToMM(t.GetPosition().x)-67.65)<.001 and abs(p.ToMM(t.GetPosition().y)-40.9)<.001
    if incident or old_via:
        removed.append({'uuid': t.m_Uuid.AsString(), 'net': t.GetNetname()})
        held.append(t)
        b.Remove(t)
f.SetPosition(p.VECTOR2I(p.FromMM(70), p.FromMM(43)))
f.SetOrientationDegrees(0)
d = next(d for d in fps['U18'].Pads() if d.GetNumber() == '7')
path = [(p.ToMM(d.GetPosition().x), p.ToMM(d.GetPosition().y)), (67.4,40.25), (68.1,40.95), (68.5,41.35)]
for a,z in zip(path,path[1:]):
    t = p.PCB_TRACK(b)
    t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])))
    t.SetEnd(p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1])))
    t.SetLayer(p.B_Cu)
    t.SetWidth(p.FromMM(.25))
    t.SetNetCode(d.GetNetCode())
    t.SetLocked(True)
    b.Add(t)
v = p.PCB_VIA(b)
v.SetPosition(p.VECTOR2I(p.FromMM(68.5),p.FromMM(41.35)))
v.SetWidth(p.FromMM(.9))
v.SetDrill(p.FromMM(.3))
v.SetViaType(p.VIATYPE_THROUGH)
v.SetLayerPair(p.F_Cu,p.B_Cu)
v.SetNetCode(d.GetNetCode())
v.SetLocked(True)
b.Add(v)
assert contract() == before
data = json.loads((OUT/'design.json').read_text(encoding='utf-8'))
for q in data['parts']:
    if q['ref']=='C73':
        q.update(x=70,y=43,angle=0,side='B')
data['two_layer_iterations'].append({'snapshot':str(snap.relative_to(OUT)),
    'reason':'Keep boost decoupling clear of staggered system-output power via',
    'moves':{'C73':[70,43,0,'B']}})
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE),b)
(OUT/'exports/mux-output-refinement.json').write_text(json.dumps({'removed':removed,'SYS5_fanout_mm':path},indent=2),encoding='utf-8')
for t in held:
    t.thisown=False
print('Restored reviewed output dogleg; independent DRC and current-path review required.')
