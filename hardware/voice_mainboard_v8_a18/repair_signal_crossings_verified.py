"""Reroute a short connected signal chain around native clearance findings.

Keep all other nets and all pads. Extend past blocked endpoints before asking
the two-layer router for a replacement. Each accepted replacement must reduce
native hard findings, preserve pad connectivity and preserve protected rails.
"""
import datetime
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from comparison_route_geometry import b, FILE, p, pos, polys, layers, route, required_clearance
from repair_comparison_groups import groups
from route_net_classes import PROTECTED
from shapely.geometry import Point, LineString

selected=set(filter(None,os.environ['A18_CROSSING_NETS'].split(',')))
assert selected and not selected.intersection(PROTECTED)
out=FILE.parent/'iterations'/('verified-crossing-repair-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True);shutil.copy2(FILE,out/FILE.name)
cli=Path(__file__).resolve().parents[2]/'build/cad-tools/kicad/bin/kicad-cli.exe'
def check():
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    dest=out/'native.json'
    subprocess.run([str(cli),'pcb','drc','--format','json','--output',str(dest),str(FILE)],check=True,capture_output=True)
    return json.loads(dest.read_text(encoding='utf-8'))
def hard(r):
    return [q for q in r['violations'] if q['type'] not in ('track_dangling','via_dangling')]
def xy(v):return (p.ToMM(v.x),p.ToMM(v.y))
def key(v):return (int(v.x),int(v.y))
def endpoints(t):return [t.GetStart(),t.GetEnd()]
def terminal(net,layer,point):
    pt=Point(xy(point))
    for f in b.GetFootprints():
        for d in f.Pads():
            if d.GetNetname()==net and d.IsOnLayer(layer) and any(sh.buffer(.001).covers(pt) for sh in polys(d,layer)):return True
    return any(isinstance(t,p.PCB_VIA) and t.GetNetname()==net and math.dist(pos(t),xy(point))<.001 for t in b.GetTracks())
def blocked(net,layer,point,width):
    pt=Point(xy(point))
    for f in b.GetFootprints():
        for d in f.Pads():
            if d.GetNetname()!=net and d.IsOnLayer(layer):
                if any(sh.distance(pt)<required_clearance(net,d.GetNetname())+width/2 for sh in polys(d,layer)):return True
    for t in b.GetTracks():
        if t.GetNetname()==net or not t.IsOnLayer(layer):continue
        sh=Point(pos(t)) if isinstance(t,p.PCB_VIA) else LineString([xy(t.GetStart()),xy(t.GetEnd())])
        radius=p.ToMM(t.GetWidth(layer) if isinstance(t,p.PCB_VIA) else t.GetWidth())/2
        if sh.distance(pt)<radius+width/2+required_clearance(net,t.GetNetname()):return True
    return False
report=check();changes=[];rejected=set();held=[]
for iteration in range(12):
    objects={t.m_Uuid.AsString():t for t in b.GetTracks()}
    candidates=[]
    for finding in hard(report):
        for item in finding['items']:
            t=objects.get(item['uuid'])
            if t is not None and not isinstance(t,p.PCB_VIA) and t.GetNetname() in selected:
                if t.m_Uuid.AsString() not in rejected:candidates.append(t)
    accepted=False
    for first in candidates:
        net=first.GetNetname();layer=first.GetLayer();width=p.ToMM(first.GetWidth())
        siblings=[t for t in b.GetTracks() if not isinstance(t,p.PCB_VIA) and t.GetNetname()==net and t.GetLayer()==layer]
        chunk={first.m_Uuid.AsString():first}
        for expand in range(80):
            counts={};vectors={}
            for t in chunk.values():
                for v in endpoints(t):
                    k=key(v);counts[k]=counts.get(k,0)+1;vectors[k]=v
            ends=[vectors[k] for k,n in counts.items() if n==1]
            if len(ends)!=2:break
            length=sum(p.ToMM(t.GetLength()) for t in chunk.values())
            choices=[]
            for v in ends:
                if terminal(net,layer,v):continue
                need=blocked(net,layer,v,width) or length<1.5
                if need:
                    others=[t for t in siblings if t.m_Uuid.AsString() not in chunk and any(key(q)==key(v) for q in endpoints(t))]
                    if len(others)==1:choices.append(others[0])
            if not choices:break
            for t in choices:chunk[t.m_Uuid.AsString()]=t
        if len(ends)!=2 or any(blocked(net,layer,v,width) for v in ends):
            rejected.add(first.m_Uuid.AsString());continue
        before_groups={n:len(groups(n)) for n in {net,*[q for q in PROTECTED if b.FindNet(q)]}}
        original_ids=set(objects);removed=list(chunk.values())
        for t in removed:b.Remove(t)
        a,z=map(xy,ends)
        try:
            result=route(net,a,z,{layers.index(layer)},{layers.index(layer)},width=width,step=.075,
                bounds=(max(.5,min(a[0],z[0])-5),max(.5,min(a[1],z[1])-5),min(72.5,max(a[0],z[0])+5),min(72.5,max(a[1],z[1])+5)))
            candidate=check()
            after_groups={n:len(groups(n)) for n in before_groups}
            valid=(len(hard(candidate))<len(hard(report))
                   and len(candidate['unconnected_items'])<=len(report['unconnected_items'])
                   and all(after_groups[n]<=before_groups[n] for n in before_groups))
            if valid:
                changes.append({'net':net,'removed_segments':len(removed),'from':a,'to':z,**result,
                    'hard_before_after':[len(hard(report)),len(hard(candidate))]})
                held.extend(removed);report=candidate;accepted=True
                print('Repaired',net,'hard',len(hard(report)),'unconnected',len(report['unconnected_items']),flush=True)
                break
        except RuntimeError:
            pass
        new=[t for t in b.GetTracks() if t.m_Uuid.AsString() not in original_ids]
        for t in new:b.Remove(t);t.thisown=False
        for t in removed:b.Add(t)
        b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
        rejected.add(first.m_Uuid.AsString())
    if not accepted:break
report=check()
for t in held:t.thisown=False
summary={'changes':changes,'rejected_chain_candidates':len(rejected),
    'hard_findings_remaining':hard(report),'native_unconnected':len(report['unconnected_items']),
    'native_findings':len(report['violations'])}
(FILE.parent/'exports/crossing-chain-repair.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2),flush=True)
