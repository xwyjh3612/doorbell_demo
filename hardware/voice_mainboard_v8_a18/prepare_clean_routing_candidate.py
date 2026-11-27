"""Create an isolated routing candidate from the reviewed real placement.

Use the immutable placement copy plus the current position manifest, avoiding
concurrent reads of a board being routed. All real pads and nets are retained.
"""
from pathlib import Path
import datetime,json,shutil
import pcbnew as p

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'two_layer_work'
OUT=ROOT/'routing_candidate'
FILE=OUT/'voice_mainboard_a18_2layer.kicad_pcb'
assert not FILE.exists(),'Do not overwrite an existing candidate'
OUT.mkdir(exist_ok=True)
for directory in ['exports','iterations']:(OUT/directory).mkdir(exist_ok=True)
for name in ['voice_mainboard_a18_2layer.kicad_sch','voice_mainboard_a18_2layer.kicad_pro','voice_mainboard_a18_2layer.kicad_dru','fp-lib-table','sym-lib-table']:
    shutil.copy2(SOURCE/name,OUT/name)
data=json.loads((SOURCE/'design.json').read_text(encoding='utf-8'))
b=p.LoadBoard(str(SOURCE/'exports/placement-only.kicad_pcb'))
fps={f.GetReference():f for f in b.GetFootprints()}
for q in data['parts']:
    f=fps[q['ref']]
    target=p.B_Cu if q['side']=='B'else p.F_Cu
    if f.GetLayer()!=target:f.Flip(f.GetPosition(),False)
    f.SetPosition(p.VECTOR2I(p.FromMM(q['x']),p.FromMM(q['y'])))
    f.SetOrientationDegrees(q['angle'])
    assert f.GetValue()==q['value']
    for d in f.Pads():
        expected=q['pins'].get(d.GetNumber(),'')
        assert d.GetNetname()==expected or not expected and d.GetNetname().startswith('unconnected-')
held=[]
for t in list(b.GetTracks()):held.append(t);b.Remove(t)
for z in list(b.Zones()):
    if not z.GetIsRuleArea():held.append(z);b.Remove(z)
assert b.GetCopperLayerCount()==2
data['revision']='A18 ISOLATED CLEAN ROUTING CANDIDATE'
data['status']='UNRELEASED; FULL ROUTING AND NATIVE REVIEW REQUIRED'
data['manufacturing_ready']=False
data['routing_candidate_created_at']=datetime.datetime.now().astimezone().isoformat()
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
# Preserve deliberately staggered power/control landings at the dense selector.
def fanout(number,points,diameter=0,drill=.2,width=.25):
    d=next(d for d in fps['U18'].Pads()if d.GetNumber()==str(number))
    path=[(p.ToMM(d.GetPosition().x),p.ToMM(d.GetPosition().y)),*points]
    for a,z in zip(path,path[1:]):
        t=p.PCB_TRACK(b);t.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])))
        t.SetEnd(p.VECTOR2I(p.FromMM(z[0]),p.FromMM(z[1])))
        t.SetWidth(p.FromMM(width));t.SetLayer(p.B_Cu);t.SetNetCode(d.GetNetCode());t.SetLocked(True);b.Add(t)
    if diameter:
        v=p.PCB_VIA(b);v.SetPosition(p.VECTOR2I(p.FromMM(path[-1][0]),p.FromMM(path[-1][1])))
        v.SetWidth(p.FromMM(diameter));v.SetDrill(p.FromMM(drill));v.SetLayerPair(p.F_Cu,p.B_Cu)
        v.SetViaType(p.VIATYPE_THROUGH);v.SetNetCode(d.GetNetCode());v.SetLocked(True);b.Add(v)
fanout(3,[(64.6,39.75),(64.05,40.3),(64,40.3)],.9,.3)
fanout(2,[(66.74,40.25)])
fanout(5,[(67.4,39.25),(67.4,38.45),(67.25,38.3)],.9,.3)
fanout(6,[(68.05,39.75),(68.5,40.2)],.9,.3)
fanout(7,[(67.4,40.25),(68.1,40.95),(68.5,41.35)],.9,.3)
fanout(1,[(65.9,40.75),(65.9,41.65),(66,41.75)],.45,.2,.16)
fanout(4,[(64.8,39.25),(64.2,38.65),(64.2,38.2)],.45,.2,.16)
fanout(8,[(67.3,40.75),(67.3,41.8)],.45,.2,.16)
b.BuildConnectivity();p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
print('Created isolated two-layer routing candidate with unchanged real placement and pads.')
