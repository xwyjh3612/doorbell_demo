"""Rebuild the broken charger TEMP network from its actual component pads."""
from pathlib import Path
import json,sys,math
import pcbnew as p
root=Path(__file__).resolve().parent
network=sys.argv[1]if len(sys.argv)>1 else'UPS_TEMP'
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
from route_multilayer import route
b=r.board;held=list(b.GetTracks())
for t in held:
    if t.GetNetname()==network:b.Remove(t)
pairs=[(f.GetReference(),pd.GetNumber())for f in b.GetFootprints()for pd in f.Pads()if pd.GetNetname()==network]
report=[];escapes={}
try:
    if network=='NTC_PACK':
        try:
            layer=p.F_Cu if r.pad('R37',2).IsOnLayer(p.F_Cu)else p.B_Cu
            r.route(('R37',2),('J4',1),layer=layer,width=.2,step=.025,bounds=(1.6,48,20,72))
            report.append({'from':['R37',2],'to':['J4',1],'layer':b.GetLayerName(layer),'width_mm':.2,'fine_grid_mm':.025})
            pairs=[]
        except RuntimeError:pass
    for pair in pairs:
        if r.pad(*pair).GetAttribute()==p.PAD_ATTRIB_PTH:escapes[pair]=pair;continue
        name='temp_'+pair[0]+'_'+pair[1];r.escapevia(name,pair,neck=.2);escapes[pair]=(name,0)
    connected={pairs[0]}if pairs else set();todo=set(pairs)-connected
    while todo:
        _,a,z=min((math.dist(r.pos(r.pad(*escapes[a])),r.pos(r.pad(*escapes[z]))),a,z)for a in connected for z in todo)
        details=route(r,escapes[a],escapes[z],width=.2)
        report.append({'from':a,'to':z,**details});connected.add(z);todo.remove(z)
finally:
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    (root/('exports/charger-'+network+'-routes.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
