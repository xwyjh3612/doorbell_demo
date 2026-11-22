"""Connect the relocated comparator's real low-frequency pin networks.

Each small net is rebuilt by a minimum-length pad spanning tree; all pads on
that net must subsequently be connected in KiCad's independent connectivity
check. No signal uses the In1 reference layer.
"""
from pathlib import Path
import sys,json,math
import pcbnew as p
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
from route_multilayer import route
b=r.board
file=root/'exports/control-signal-routes.json'
report=json.loads(file.read_text(encoding='utf8'))['branches']if file.exists()else[]
try:
    for net in ['UPS_REF_1V24','UPS_BOOST_EN','UPS_REF_0V62','UPS_BAT_UV_SENSE','UPS_EXT_SENSE','UPS_EXT_VALID','UPS_PG_OD','UPS_CHG_CE','CHG_DISABLE_IO38','DONE_OD']:
        pairs=[(fp.GetReference(),int(pd.GetNumber()))for fp in b.GetFootprints()for pd in fp.Pads()if pd.GetNetname()==net]
        todo=set(pairs);connected={min(todo)};todo-=connected
        while todo:
            _,a,z=min((math.dist(r.pos(r.pad(*a)),r.pos(r.pad(*z))),a,z)for a in connected for z in todo)
            if not any(x['net']==net and tuple(x['from'])==a and tuple(x['to'])==z for x in report):
                aa,zz=r.pos(r.pad(*a)),r.pos(r.pad(*z))
                starts,ends=a,z
                for pair,is_start in [(a,True),(z,False)]:
                    if pair[0]=='U10':
                        item=next(x for x in json.loads((root/'exports/mux-fanout.json').read_text(encoding='utf8'))['pins']if x['pin']==pair[1])
                        name='mux_'+str(pair[1]);r.virtual[name]=r.Endpoint(item['net'],item['via_mm'])
                        if is_start:starts=(name,0)
                        else:ends=(name,0)
                    elif net=='DONE_OD'and r.pad(*pair).GetAttribute()==p.PAD_ATTRIB_SMD:
                        name='done_'+pair[0]+'_'+str(pair[1])
                        if name not in r.virtual:
                            fanoutfile=root/'exports/done-fanout.json'
                            fanouts=json.loads(fanoutfile.read_text(encoding='utf8'))if fanoutfile.exists()else{}
                            if name in fanouts:r.virtual[name]=r.Endpoint(net,fanouts[name])
                            else:
                                r.escapevia(name,pair,neck=.2);fanouts[name]=r.pos(r.virtual[name]);fanoutfile.write_text(json.dumps(fanouts,indent=2)+'\n',encoding='utf8')
                        if is_start:starts=(name,0)
                        else:ends=(name,0)
                bounds=(max(1.6,min(aa[0],zz[0])-6),max(1.6,min(aa[1],zz[1])-6),min(98.4,max(aa[0],zz[0])+6),min(73.4,max(aa[1],zz[1])+6))
                try:details=route(r,starts,ends,width=.2,bounds=bounds)
                except RuntimeError:details=route(r,starts,ends,width=.2)
                report.append({'net':net,'from':a,'to':z,**details})
            connected.add(z);todo.remove(z)
finally:
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    file.write_text(json.dumps({'branches':report,'In1_signal_tracks':0,'hardware_validated':False},indent=2)+'\n',encoding='utf8')
