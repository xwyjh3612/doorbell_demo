"""Move the DC face to the case wall and give its solder lands real room.

Isolated trial: move only J1/J15, retain all parts, lands and pin contracts.
Native KiCad identifies displaced copper; never remove or relabel a pad to
make room. Every affected net must subsequently be restored and independently
checked before this layout can replace the working board.
"""
import datetime
import json
from pathlib import Path
import shutil
import subprocess
from comparison_route_geometry import b,FILE,p

repo=Path(__file__).resolve().parents[2]
cli=repo/'build/cad-tools/kicad/bin/kicad-cli.exe'
snapshot=FILE.parent/'iterations'/('connector-access-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
for f in [FILE,FILE.parent/'design.json']:
    shutil.copy2(f,snapshot/f.name)
placements={'J1':(79.0,46.0,180.0,p.B_Cu),'J15':(58.0,52.25,90.0,p.F_Cu)}
fps={f.GetReference():f for f in b.GetFootprints()}
before={r:{d.GetNumber():d.GetNetname()for d in fps[r].Pads()}for r in placements}
assert before['J1']['4']=='VIN_DC' and before['J1']['2']=='GND'
assert before['J15']=={'1':'SPK_PLUS','2':'SPK_MINUS'}
for ref,(x,y,angle,layer)in placements.items():
    f=fps[ref];assert f.GetLayer()==layer
    f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));f.SetOrientationDegrees(angle)
    assert {d.GetNumber():d.GetNetname()for d in f.Pads()}==before[ref]
movedpads={d.m_Uuid.AsString()for ref in placements for d in fps[ref].Pads()}
tracks={t.m_Uuid.AsString():t for t in b.GetTracks()}
out=FILE.parent/'exports'
def check(name):
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    file=out/(name+'.json')
    subprocess.run([str(cli),'pcb','drc','--format','json','--schematic-parity','--output',str(file),str(FILE)],capture_output=True,check=True)
    return json.loads(file.read_text(encoding='utf-8'))
native=check('connector-access-before-reroute')
retire=set();unfixable=[]
for finding in native['violations']:
    if finding['type']in('via_dangling','track_dangling'):continue
    ids={q['uuid']for q in finding['items']}
    touched=ids&movedpads
    affected=ids&tracks.keys()
    if touched and affected:
        retire.update(affected)
    else:
        unfixable.append(finding)
if unfixable:
    print(json.dumps({'unfixable_by_copper_reroute':unfixable},ensure_ascii=False,indent=2),flush=True)
    shutil.copy2(snapshot/FILE.name,FILE)
    raise SystemExit('Connector geometry conflicts with a fixed part or drawing; trial not retained')
held=[];record=[]
for uid in sorted(retire):
    t=tracks[uid];record.append({'uuid':uid,'net':t.GetNetname(),'via':isinstance(t,p.PCB_VIA)})
    b.Remove(t);held.append(t)
after=check('connector-access-retired-copper')
assert not [v for v in after['violations']if v['type']not in('via_dangling','track_dangling')], after['violations']
designfile=FILE.parent/'design.json';design=json.loads(designfile.read_text(encoding='utf-8'))
for q in design['parts']:
    if q['ref']in placements:
        x,y,a,l=placements[q['ref']];q.update(x=x,y=y,angle=a,side='F'if l==p.F_Cu else'B')
design['mechanical']['jack_access']={'mouth_x_mm':79.0,'mouth_y_mm':46.0,'PCB_right_edge_mm':73,
    'component_overhang_mm':6.0,'assumed_case_outer_wall_x_mm':79.0,
    'nominal_face_recess_mm':0.0,'case_window_mm':[9.5,11.5],
    'case_window_height_and_actual_wall_require_physical_verification':True}
designfile.write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
report={'moved_parts':list(placements),'pin_contracts_unchanged':before,'retired_copper':record,
    'affected_nets':sorted({q['net']for q in record}|{'VIN_DC','SPK_PLUS','SPK_MINUS'}),
    'native_unconnected_after_retirement':len(after['unconnected_items']),
    'snapshot':str(snapshot),'manufacturing_ready':False}
(out/'connector-access-relayout.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for t in held:t.thisown=False
print(json.dumps(report,indent=2),flush=True)
