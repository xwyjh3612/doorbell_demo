"""Evaluate a local clock dogleg while preserving its physical endpoints.

Each step is checked by KiCad. No component nets or manufacturing rules change.
"""
import json
import os
from pathlib import Path
import subprocess
import pcbnew as p

root=Path(__file__).resolve().parents[2]
file=Path(os.environ['A18_REPAIR_BOARD']).resolve()
original=file.read_bytes();records=[]
manager=p.GetSettingsManager();manager.LoadProject(str(file.with_suffix('.kicad_pro')))
for dy in (-.25,-.3,-.35,-.4,-.45,-.5):
    file.write_bytes(original);b=p.LoadBoard(str(file))
    b.SetProject(manager.GetProject(str(file.with_suffix('.kicad_pro'))));b.SynchronizeNetsAndNetClasses(False)
    old=next(t for t in b.GetTracks()if t.m_Uuid.AsString()=='3d92404c-4de9-427a-b28c-cef8ae37167b')
    assert old.GetNetname()=='I2S_SPK_BCLK15'
    a,z=old.GetStart(),old.GetEnd();path=[a,p.VECTOR2I(a.x,a.y+p.FromMM(dy)),p.VECTOR2I(z.x,z.y+p.FromMM(dy)),z]
    width=old.GetWidth();layer=old.GetLayer();net=old.GetNetCode();b.Remove(old)
    for s,e in zip(path,path[1:]):
        t=p.PCB_TRACK(b);t.SetStart(s);t.SetEnd(e);t.SetWidth(width);t.SetLayer(layer);t.SetNetCode(net);b.Add(t)
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b);old.thisown=False
    reportfile=file.parent/'exports'/'clock-jog-native.json'
    subprocess.run([str(root/'build/cad-tools/kicad/bin/kicad-cli.exe'),'pcb','drc','--format','json','--output',str(reportfile),str(file)],check=True,capture_output=True)
    r=json.loads(reportfile.read_text(encoding='utf-8'));hard=[v for v in r['violations']if v['type']not in('via_dangling','track_dangling')]
    records.append({'dy':dy,'hard':hard,'unconnected':len(r['unconnected_items'])})
    print('Clock offset',dy,'hard',len(hard),flush=True)
    if not hard:break
else:file.write_bytes(original)
(file.parent/'exports'/'clock-jog-trials.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
