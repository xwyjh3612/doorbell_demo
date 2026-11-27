"""Reuse ordinary signal geometry in a separate, reviewed power layout.

Run export and import in separate processes so KiCad's project settings manager
cannot mix the two projects. This never transfers power or ground, footprints,
net definitions, or rules. Imported geometry needs native DRC and repair.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pcbnew as p

from route_net_classes import PROTECTED
mode, board_arg, json_arg = sys.argv[1:]
board_path, json_path = Path(board_arg).resolve(), Path(json_arg).resolve()
b = p.LoadBoard(str(board_path))
if mode == 'export':
    records = []
    for t in b.GetTracks():
        if not t.GetNetname() or t.GetNetname() in PROTECTED:
            continue
        q = {'net': t.GetNetname(), 'via': isinstance(t, p.PCB_VIA)}
        if q['via']:
            q.update(x=t.GetPosition().x, y=t.GetPosition().y,
                     width=t.GetWidth(p.F_Cu), drill=t.GetDrill())
        else:
            q.update(ax=t.GetStart().x, ay=t.GetStart().y,
                     zx=t.GetEnd().x, zy=t.GetEnd().y,
                     width=t.GetWidth(), layer=t.GetLayer())
        records.append(q)
    report = {'source': str(board_path),
              'source_sha256': hashlib.sha256(board_path.read_bytes()).hexdigest(),
              'protected_nets': sorted(PROTECTED), 'copper': records}
    json_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Exported ordinary signal copper:', len(records))
elif mode == 'import':
    manager = p.GetSettingsManager()
    project = board_path.with_suffix('.kicad_pro')
    assert manager.LoadProject(str(project))
    b.SetProject(manager.GetProject(str(project)))
    b.SynchronizeNetsAndNetClasses(False)
    assert b.GetCopperLayerCount() == 2
    data = json.loads(json_path.read_text(encoding='utf-8'))
    snapshot = board_path.parent/'iterations'/('before-signal-transfer-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    snapshot.mkdir(parents=True)
    shutil.copy2(board_path, snapshot/board_path.name)
    # Replace this selected class only. Snapshot retains old ordinary escapes;
    # the source contributes the complete class rather than duplicate vias.
    replaced = []
    for t in list(b.GetTracks()):
        if t.GetNetname() not in PROTECTED:
            replaced.append(t)
            b.Remove(t)
    for q in data['copper']:
        assert q['net'] not in PROTECTED
        if q['via']:
            t = p.PCB_VIA(b)
            t.SetPosition(p.VECTOR2I(q['x'], q['y']))
            t.SetWidth(q['width']); t.SetDrill(q['drill'])
            t.SetViaType(p.VIATYPE_THROUGH)
            t.SetLayerPair(p.F_Cu, p.B_Cu)
        else:
            t = p.PCB_TRACK(b)
            t.SetStart(p.VECTOR2I(q['ax'], q['ay']))
            t.SetEnd(p.VECTOR2I(q['zx'], q['zy']))
            t.SetWidth(q['width']); t.SetLayer(q['layer'])
        t.SetNetCode(b.FindNet(q['net']).GetNetCode())
        t.SetLocked(False)
        b.Add(t)
    b.BuildConnectivity()
    assert p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(board_path), b)
    print('Imported ordinary signal copper; native review required:', len(data['copper']),
          '; replaced old ordinary items:', len(replaced))
else:
    raise ValueError(mode)
