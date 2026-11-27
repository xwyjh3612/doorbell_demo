"""Restore filled ground connectivity for the isolated RGB candidate."""
import hashlib,json,sys,types
from pathlib import Path
import pcbnew as p
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'indicator_revision';FILE=OUT/'voice_mainboard_v7.kicad_pcb'
# Reuse the candidate router's power/antenna-aware helpers, without executing
# its mutations. Its helper setup ends immediately before design.json loading.
src=(ROOT/'add_indicator_candidate.py').read_text(encoding='utf-8')
start=src.index("source=(ROOT.parent/");end=src.index("data=json.loads(")
setup='import collections,hashlib,json,re,shutil,sys,types,uuid\nfrom pathlib import Path\nimport pcbnew as p\nROOT=Path(__file__).resolve().parent\nREPO=ROOT.parents[1]\nOUT=ROOT/"indicator_revision"\nFILE=OUT/"voice_mainboard_v7.kicad_pcb"\n'+src[start:end]
setup=setup.replace("zone.GetNetname() not in ['GND',net]:","zone.GetNetname() not in ['GND',net] and net!='GND':")
rmod=types.ModuleType('rgb_ground_finish');rmod.__dict__['__file__']=__file__
exec(compile(setup,'rgb_ground_helpers','exec'),rmod.__dict__)
r=rmod.r;b=r.board;held=[];changes=[]
dr=json.loads((OUT/'exports/drc.json').read_text(encoding='utf-8'))
for v in dr['violations']:
    if v['type']=='via_dangling':
        for i in v['items']:
            t=next(t for t in b.GetTracks()if t.m_Uuid.AsString()==i['uuid'])
            assert isinstance(t,p.PCB_VIA)and t.GetNetname()=='STATUS_LED_IO39'
            held.append(t);b.Remove(t);changes.append({'removed_one_layer_via':i['uuid']})
# Move label only, without moving its electrical test pad.
next(fp for fp in b.GetFootprints()if fp.GetReference()=='TP1').Reference().SetPosition(p.VECTOR2I(p.FromMM(74),p.FromMM(9)))
groups=json.loads((OUT/'ground-components.json').read_text(encoding='utf-8'))
main_vias={v['uuid']for v in groups[0]['vias']}
targets=[t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.m_Uuid.AsString()in main_vias and 35<=r.pos(t)[0]<=60 and 15<=r.pos(t)[1]<=58]
for index,g in enumerate(groups[1:]):
    existing={v['uuid']for v in g['vias']}
    candidates=[t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and t.m_Uuid.AsString()in existing]
    if not candidates:
        pd=g['pads'][0];label=f'ground_island_{index}'
        if pd['ref']=='U4' and pd['pad']=='2':
            r.route(('U4',2),('U4',5),layer=p.F_Cu,width=.2,step=.025,bounds=(42,23,49,27))
            changes.append({'ground_bridge':['U4.2','U4.5'],'width_mm':.2});continue
        r.escapevia(label,(pd['ref'],pd['pad']),diameter=.5,drill=.3,neck=.18)
        changes.append({'added_ground_return':[pd['ref'],pd['pad']],'via_mm':r.pos(r.virtual[label])})
        continue
    a=candidates[0];r.virtual['ground_island_source']=a
    paired=sorted(targets,key=lambda t:(r.pos(t)[0]-r.pos(a)[0])**2+(r.pos(t)[1]-r.pos(a)[1])**2)
    done=False
    for z in paired[:15]:
        r.virtual['ground_main_target']=z
        for layer in [p.B_Cu,p.F_Cu]:
            try:r.route(('ground_island_source',0),('ground_main_target',0),layer=layer,width=.25,step=.05,bounds=(35,15,60,58))
            except(RuntimeError,AssertionError):continue
            changes.append({'ground_bridge_mm':[r.pos(a),r.pos(z)],'layer':b.GetLayerName(layer)});done=True;break
        if done:break
        if all(35<=r.pos(t)[0]<=60 and 15<=r.pos(t)[1]<=58 for t in [a,z]):
            try:rmod.m.route(r,('ground_island_source',0),('ground_main_target',0),width=.25,step=.1,bounds=(35,15,60,58))
            except(RuntimeError,AssertionError):continue
            changes.append({'ground_bridge_mm':[r.pos(a),r.pos(z)],'layer':'F/B checked routing'});done=True;break
    assert done,('No checked local ground path',index)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
for t in held:t.thisown=False
(OUT/'exports/rgb-ground-changes.json').write_text(json.dumps({'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'changes':changes},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(changes,ensure_ascii=False,indent=2))
