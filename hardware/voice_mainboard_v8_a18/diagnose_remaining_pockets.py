"""Read-only discrete reachability for the currently isolated signal endpoint.

Planning geometry is not a native DRC result. This never saves the board.
"""
import json
import math
import os
from pathlib import Path
from comparison_route_geometry import b,FILE,p,pos,layers,route
from repair_comparison_groups import groups
import numpy as np

out=FILE.parent/'exports'
records=[]
for net in os.environ['A18_ONLY_NETS'].split(','):
    gs=groups(net,add_track_anchors=True)
    if len(gs)<2:continue
    gs.sort(key=len)
    if os.environ.get('A18_DIAG_LARGE_GROUP')=='1':gs.reverse()
    src=min(gs[0],key=lambda q:not isinstance(q,p.PAD))
    target=min(gs[1],key=lambda q:math.dist(pos(q),pos(src)))
    diag=out/('reachable-'+net+'.npz')
    os.environ['A18_ROUTE_DIAGNOSTIC_FILE']=str(diag)
    record={'net':net,'src':pos(src),'goal':pos(target),'layers':[]}
    existing={t.m_Uuid.AsString()for t in b.GetTracks()}
    try:
        q=route(net,pos(src),pos(target),{i for i,l in enumerate(layers)if src.IsOnLayer(l)},
                {i for i,l in enumerate(layers)if target.IsOnLayer(l)},
                width=.16 if net=='M_USB_DP'else .12,step=.05)
        record['route_found_in_memory_only']=q
    except RuntimeError as error:
        record['error']=str(error)
        if diag.exists():
            data=np.load(diag)
            for i in range(len(layers)):
                y,x=np.where(data['reachable'][i])
                record['layers'].append({'layer':p.LayerName(layers[i]),'points':len(x),
                    'bounds':None if not len(x)else [float(data['xs'][x].min()),float(data['ys'][y].min()),float(data['xs'][x].max()),float(data['ys'][y].max())]})
    for t in list(b.GetTracks()):
        if t.m_Uuid.AsString()not in existing:
            b.Remove(t);t.thisown=False
    records.append(record)
    print(json.dumps(record),flush=True)
    (out/'remaining-pockets.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
