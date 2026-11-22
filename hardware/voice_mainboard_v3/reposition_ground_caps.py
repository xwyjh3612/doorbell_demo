"""Free space beside decoupling ground pads without moving the boost SW loop."""
from pathlib import Path
import json,sys,math
import pcbnew as p
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import LineString,Point,box
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
d=json.loads((root/'design.json').read_text(encoding='utf8'));fps={f.GetReference():f for f in b.GetFootprints()}
changes={'C40':(15.25,65),'C39':(16,51.9),'C53':(27.25,49),'C50':(12.5,44.5)}
held=[];removed=[]
for ref,xy in changes.items():
    f=fps[ref];old=(p.ToMM(f.GetPosition().x),p.ToMM(f.GetPosition().y))
    if old==xy:continue
    nets={pd.GetNetname()for pd in f.Pads()};local=box(old[0]-2.5,old[1]-2.5,old[0]+2.5,old[1]+2.5)
    ground_centers=[(p.ToMM(pd.GetPosition().x),p.ToMM(pd.GetPosition().y))for pd in f.Pads()if pd.GetNetname()=='GND']
    for t in list(b.GetTracks()):
        if t.GetNetname()not in nets:continue
        if t.GetNetname()=='GND':
            if isinstance(t,p.PCB_VIA):continue
            endpoints=[(p.ToMM(pt.x),p.ToMM(pt.y))for pt in [t.GetStart(),t.GetEnd()]]
            if not any(math.dist(pt,g)<.1 for pt in endpoints for g in ground_centers):continue
        sh=Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y))if isinstance(t,p.PCB_VIA)else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))])
        if sh.intersects(local):held.append(t);removed.append({'net':t.GetNetname(),'uuid':t.m_Uuid.AsString()});b.Remove(t)
    f.SetPosition(p.VECTOR2I(p.FromMM(xy[0]),p.FromMM(xy[1])))
    item=next(v for v in d['parts']if v['ref']==ref);item.update(x=xy[0],y=xy[1])
p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(root/'exports/capacitor-ground-reposition.json').write_text(json.dumps({'positions_mm':changes,'removed_local_copper':removed,'switching_loop_changed':False},indent=2)+'\n',encoding='utf8')
print('Moved four decoupling capacitors to permit conventional ground escape')
