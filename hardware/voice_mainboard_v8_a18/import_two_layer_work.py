"""Import isolated router result; all native checks remain mandatory."""
from pathlib import Path
import json, os, shutil
import pcbnew as p
FILE = Path(os.environ['A18_REPAIR_BOARD']).resolve()
OUT = FILE.parent
shutil.copy2(FILE, OUT / 'before-router-import.kicad_pcb')
b = p.LoadBoard(str(FILE))
manager=p.GetSettingsManager();assert manager.LoadProject(str(FILE.with_suffix('.kicad_pro')))
b.SetProject(manager.GetProject(str(FILE.with_suffix('.kicad_pro'))));b.SynchronizeNetsAndNetClasses(False)
assert b.GetCopperLayerCount() == 2
scope_file=OUT/'exports/router-input-scope.json'
retain_ground=scope_file.exists() and json.loads(scope_file.read_text(encoding='utf-8')).get('actual_ground_copper_retained_as_fixed_obstacles')
ground=[]
if retain_ground:
    for t in b.GetTracks():
        if t.GetNetname()!='GND':continue
        q={'uuid':t.m_Uuid.AsString(),'locked':t.IsLocked(),'via':isinstance(t,p.PCB_VIA)}
        if q['via']:q.update(x=t.GetPosition().x,y=t.GetPosition().y,width=t.GetWidth(p.F_Cu),drill=t.GetDrill(),kind=t.GetViaType())
        else:q.update(ax=t.GetStart().x,ay=t.GetStart().y,zx=t.GetEnd().x,zy=t.GetEnd().y,width=t.GetWidth(),layer=t.GetLayer())
        ground.append(q)
    (OUT/'exports/pre-import-ground-copper.json').write_text(json.dumps(ground,indent=2),encoding='utf-8')
assert p.ImportSpecctraSES(b, str(OUT / 'signals.ses'))
# A skipped GROUND class can omit its fixed copper from the SES output.
# Restore the actual saved ground tracks/vias, retaining geometry and widths;
# new router copper must still pass the subsequent independent native DRC.
if retain_ground:
    present={t.m_Uuid.AsString() for t in b.GetTracks()}
    restored=0
    for t in ground:
        if t['uuid'] not in present:
            if t['via']:
                copy=p.PCB_VIA(b);copy.SetPosition(p.VECTOR2I(t['x'],t['y']))
                copy.SetWidth(t['width']);copy.SetDrill(t['drill'])
                copy.SetLayerPair(p.F_Cu,p.B_Cu);copy.SetViaType(t['kind'])
            else:
                copy=p.PCB_TRACK(b);copy.SetStart(p.VECTOR2I(t['ax'],t['ay']));copy.SetEnd(p.VECTOR2I(t['zx'],t['zy']))
                copy.SetWidth(t['width']);copy.SetLayer(t['layer'])
            copy.SetLocked(t['locked'])
            copy.SetNetCode(b.FindNet('GND').GetNetCode());b.Add(copy)
            restored+=1
    print('Restored skipped-class fixed ground copper:',restored)
data = json.loads((OUT / 'design.json').read_text(encoding='utf-8'))
project=json.loads(FILE.with_suffix('.kicad_pro').read_text(encoding='utf-8'))
ground_clearance=next(q['clearance']for q in project['net_settings']['classes']if q['name']=='Default')
held=[]
for z in list(b.Zones()):
    if not z.GetIsRuleArea() and z.GetNetname()=='GND':
        held.append(z);b.Remove(z)
for layer in [p.F_Cu, p.B_Cu]:
    z = p.ZONE(b); z.SetLayer(layer); z.SetNet(b.FindNet('GND'))
    z.SetLocalClearance(p.FromMM(ground_clearance)); z.SetMinThickness(p.FromMM(.2))
    z.SetPadConnection(p.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    z.Outline().NewOutline()
    for x, y in data['mechanical']['outline_mm']:
        z.Outline().Append(p.FromMM(x), p.FromMM(y))
    b.Add(z)
b.BuildConnectivity(); assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE), b)
for z in held:z.thisown=False
print('Imported two-layer routing and ground pours; run independent native DRC now.')
