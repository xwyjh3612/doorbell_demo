"""Reserve broad critical power paths, then export remaining two-layer routes."""
from pathlib import Path
import json, os, re, time
import pcbnew as p
from comparison_route_geometry import b,FILE,route,pos,layers
from repair_comparison_groups import groups
ROOT=FILE.parent;OUT=ROOT/'exports';OUT.mkdir(exist_ok=True)
fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,n):return next(d for d in fps[ref].Pads()if d.GetNumber()==str(n))
def via_for(ref,n):
    d=pad(ref,n);gs=groups(d.GetNetname())
    for g in gs:
        if d in g:
            vs=[x for x in g if isinstance(x,p.PCB_VIA)]
            if vs:return min(vs,key=lambda x:__import__('math').dist(pos(x),pos(d)))
    return d
pairs=[
    (('U2',3),('L1',1),.8),
    (('L1',2),('C6',1),.8), (('L1',2),('C7',1),.8),
    (('L1',2),('U1',42),.8), (('U1',42),('U1',43),.6),
    (('U2',1),('C4',1),.8), (('U2',1),('U2',4),.8),
    (('U15',3),('L4',2),.8), (('U15',4),('L4',1),.8),
    (('U15',7),('C65',1),.8), (('U15',7),('C66',1),.8),
    (('U15',7),('U18',6),.8),
    (('U18',2),('U18',7),.6),
    (('J1',4),('F1',1),1), (('F1',2),('Q6',3),.5),
    (('Q6',2),('U18',3),.8), (('U18',3),('U18',5),.6),
    (('U18',2),('U2',1),.8), (('U18',2),('U13',1),.8),
    (('U18',2),('C8',1),.8),
    (('U13',3),('L5',1),.6), (('L5',2),('C60',1),.6),
    (('U17',2),('J23',2),.8), (('J23',1),('L4',1),.8),
]
entries=[]
for a,z,width in pairs:
    da,dz=pad(*a),pad(*z);net=da.GetNetname();assert net==dz.GetNetname(),(a,z)
    if net=='BAT_BOOST_5V':
        width=float(os.environ.get('A18_BOOST_MAIN_WIDTH',width))
    if net=='UPS_SW':
        width=float(os.environ.get('A18_BOOST_SWITCH_WIDTH',width))
    connected=any(da in g and dz in g for g in groups(net))
    entry={'from':a,'to':z,'net':net,'width_mm':width,'already_connected':connected}
    if not connected:
        started=time.monotonic()
        ea,ez=via_for(*a),via_for(*z)
        attempts=[(ea,ez)]
        if os.environ.get('A18_POWER_ALTERNATE_ENDPOINTS')=='1':
            gs=groups(net)
            source=next(g for g in gs if da in g);target=next(g for g in gs if dz in g)
            # A nearby off-pad via may be connected through a neck but have no
            # room for a broad continuation. Try other connected landings.
            alternatives=sorted(((x,y)for x in source for y in target),key=lambda q:__import__('math').dist(pos(q[0]),pos(q[1])))
            attempts.extend(alternatives[:12])
        errors=[]
        for ea,ez in attempts:
            sl={i for i,l in enumerate(layers)if ea.IsOnLayer(l)};gl={i for i,l in enumerate(layers)if ez.IsOnLayer(l)}
            try:
                entry.update(route(net,pos(ea),pos(ez),sl,gl,width=width),success=True)
                entry['route_from_mm']=pos(ea);entry['route_to_mm']=pos(ez)
                break
            except RuntimeError as error:
                errors.append(str(error))
        if not entry.get('success'):
            entry.update(success=False,reason=errors[-1],alternate_attempts=len(attempts))
        entry['seconds']=time.monotonic()-started
    entries.append(entry);p.SaveBoard(str(FILE),b);print(net,a,z,entry.get('success',connected),entry.get('reason',''),flush=True)
    (OUT/'reserved-power-routes.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
assert p.ExportSpecctraDSN(b,str(ROOT/'power-first.dsn'))
text=(ROOT/'power-first.dsn').read_text(encoding='utf-8')
large=f'Via[0-{b.GetCopperLayerCount()-1}]_600:300_um';small=f'Via[0-{b.GetCopperLayerCount()-1}]_450:200_um'
if small not in text:
    at=text.index('    (padstack "'+large+'"');end=text.index('\n    )',at)+len('\n    )')
    block=text[at:end].replace(large,small).replace(' 600',' 450').replace(' 300',' 200');text=text[:end]+'\n'+block+text[end:]
text=text.replace('(use_via "'+large+'")','(use_via "'+small+'")')
text=re.sub(r'\(width 200\)', '(width 160)', text)
power=['BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','ESP_3V3','MODEM_3V8','SYS_5V','VIN_PROTECTED']
fused=['VIN_DC','VIN_FUSED']
start=text.index('    (class kicad_default');end=text.index('      (circuit',start)
head=text[start:end]
for net in power+fused:head=re.sub(r'(?<![\w])'+re.escape(net)+r'(?![\w])','',head)
text=text[:start]+head+text[end:]
extra='    (class POWER '+' '.join(power)+' (circuit (use_via "'+large+'")) (rule (width 250) (clearance 200)))\n'
extra+='    (class FUSED_INPUT '+' '.join(fused)+' (circuit (use_via "'+large+'")) (rule (width 800) (clearance 200)))\n'
text=text.replace('  )\n  (wiring',extra+'  )\n  (wiring',1)
# Primary paths were reserved above. Narrow automatically completed branches
# remain a review item; do not infer 2A qualification from connectivity.
(ROOT/'power-first.dsn').write_text(text,encoding='utf-8')
print('Exported candidate with reserved power; all remaining routes require DRC and current-path review.')
