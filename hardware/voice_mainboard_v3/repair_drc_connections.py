"""Route the disconnected islands reported by independent KiCad DRC.

Track endpoints retain their actual layer membership. Ground planes are
handled separately by stitching; a zone's displayed origin is not its island.
"""
from pathlib import Path
import json,sys
import pcbnew as p
root=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],str(root/'voice_mainboard_v3.kicad_pcb')]
import route_helpers as r
from route_multilayer import route
b=r.board
items={x.m_Uuid.AsString():x for x in b.GetTracks()}
items.update({pd.m_Uuid.AsString():pd for fp in b.GetFootprints()for pd in fp.Pads()})
d=json.loads((root/'exports/current-drc.json').read_text(encoding='utf8'));report=[]
def endpoint(item,index):
    obj=items.get(item['uuid'])
    if obj is None:return None
    if isinstance(obj,p.PAD):return(obj.GetParentFootprint().GetReference(),obj.GetNumber())
    name='repair_'+str(index);pos=obj.GetPosition()if isinstance(obj,p.PCB_VIA)else obj.GetStart()
    r.virtual[name]=r.Endpoint(obj.GetNetname(),(p.ToMM(pos.x),p.ToMM(pos.y)))
    r.virtual[name].IsOnLayer=lambda layer,obj=obj:isinstance(obj,p.PCB_VIA)or obj.GetLayer()==layer
    return(name,0)
try:
    for n,v in enumerate(d['unconnected_items']):
        a,z=[endpoint(x,n*2+i)for i,x in enumerate(v['items'])]
        if a is None or z is None:continue
        net=r.pad(*a).GetNetname()
        width=.8 if net in ['VIN_FUSED','VIN_PROTECTED']else .25 if net=='BAT_SENSE_IN'else .2
        # Prefer a single physical layer before adding vias.
        ok=False
        for layer in [p.F_Cu,p.B_Cu,p.In2_Cu]:
            if any(hasattr(r.pad(*pair),'IsOnLayer')and not r.pad(*pair).IsOnLayer(layer)for pair in [a,z]):continue
            aa,zz=r.pos(r.pad(*a)),r.pos(r.pad(*z))
            bounds=(max(1.6,min(aa[0],zz[0])-5),max(1.6,min(aa[1],zz[1])-5),min(98.4,max(aa[0],zz[0])+5),min(73.4,max(aa[1],zz[1])+5))
            try:r.route(a,z,layer=layer,width=width,step=.05,bounds=bounds);ok=True;break
            except RuntimeError:pass
        if not ok:
            try:route(r,a,z,width=width)
            except RuntimeError as e:
                report.append({'net':net,'connected':False,'reason':str(e)});print('REPAIR FAILED',net,str(e),flush=True);continue
        report.append({'net':net,'connected':True,'width_mm':width})
finally:
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    (root/'exports/drc-island-repairs.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
