"""Reserve broad, reviewed rail shortcuts before ordinary signal routing.

This keeps pad/via geometry. Native DRC decides whether a proposed path is
retained, and the electrical audit must evaluate the resulting actual copper.
"""
import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path

from comparison_route_geometry import b, FILE, p, route

plans=json.loads(os.environ['A18_POWER_SHORTCUT_PLANS'])
os.environ['A18_ROUTE_RIPUP_SIGNAL_WIRES']='1' if os.environ.get('A18_POWER_ALLOW_SIGNAL_RIPUP')=='1' else '0'
out=FILE.parent/'exports'
snapshot=FILE.parent/'iterations'/('before-power-shortcuts-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True)
shutil.copy2(FILE,snapshot/FILE.name)
cli=Path(__file__).resolve().parents[2]/'build/cad-tools/kicad/bin/kicad-cli.exe'
logs=[]
for plan in plans:
    original={t.m_Uuid.AsString():t for t in b.GetTracks()}
    existing=set(original)
    try:
        result=route(plan['net'],tuple(plan['from']),tuple(plan['to']),set(plan['from_layers']),set(plan['to_layers']),width=plan.get('width',.8),step=.1)
        b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
        subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(out/'power-shortcut-drc.json'),str(FILE)],check=True,capture_output=True)
        drc=json.loads((out/'power-shortcut-drc.json').read_text(encoding='utf-8'))
        hard=[q for q in drc['violations'] if q['type'] not in ['track_dangling','via_dangling']]
        if hard:
            raise RuntimeError('Native DRC rejected path: '+str([q['type'] for q in hard]))
    except RuntimeError as error:
        held=[]
        for t in list(b.GetTracks()):
            if t.m_Uuid.AsString() not in existing:
                held.append(t);b.Remove(t)
        # Optional signal retirement is reversible if the native guard rejects
        # the new power route. Restore every original object that was removed.
        present={t.m_Uuid.AsString() for t in b.GetTracks()}
        for uid,t in original.items():
            if uid not in present:b.Add(t)
        b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
        for t in held:t.thisown=False
        logs.append({**plan,'success':False,'error':str(error)})
    else:
        for t in b.GetTracks():
            if t.m_Uuid.AsString() not in existing:t.SetLocked(True)
        p.SaveBoard(str(FILE),b)
        logs.append({**plan,'success':True,**result})
    print(json.dumps(logs[-1]),flush=True)
(out/'power-shortcuts.json').write_text(json.dumps(logs,indent=2),encoding='utf-8')
