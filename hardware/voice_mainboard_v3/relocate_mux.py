"""Provide space for conventional mux fanout; keep boost switching loop intact.

Move the slow charging inhibit transistor to the back, then place the mux two
millimeters north. Release only local old mux copper and Q7 control nets.
"""
from pathlib import Path
import json,sys
import pcbnew as p
sys.path.insert(0,str(Path('build/cad-tools/route-python').resolve()))
from shapely.geometry import Point,LineString,box
root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
fps={f.GetReference():f for f in b.GetFootprints()};items=list(b.GetTracks());removed=[]
mux_nets={pd.GetNetname()for pd in fps['U10'].Pads()if pd.GetNetname()!='GND'}
local=box(15.3,47.8,21.5,53.1)
for t in items:
    sh=Point(p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y))if isinstance(t,p.PCB_VIA)else LineString([(p.ToMM(t.GetStart().x),p.ToMM(t.GetStart().y)),(p.ToMM(t.GetEnd().x),p.ToMM(t.GetEnd().y))])
    if t.GetNetname()in ['CHG_DISABLE_IO38','UPS_CHG_CE']or(t.GetNetname()in mux_nets and sh.intersects(local)):
        removed.append(t);b.Remove(t)
fps['U10'].SetPosition(p.VECTOR2I(p.FromMM(18),p.FromMM(48)))
if fps['Q7'].GetLayer()!=p.B_Cu:fps['Q7'].Flip(fps['Q7'].GetPosition(),True)
fps['Q7'].SetPosition(p.VECTOR2I(p.FromMM(25),p.FromMM(65)))
d=json.loads((root/'design.json').read_text(encoding='utf8'))
for item in d['parts']:
    if item['ref']=='U10':item.update(x=18,y=48)
    if item['ref']=='Q7':item.update(x=25,y=65,side='B',angle=fps['Q7'].GetOrientationDegrees())
progress=root/'exports/power-trunks.json';v=json.loads(progress.read_text(encoding='utf8'))
valid_vias=[t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)]
invalid=set()
for key,info in v.get('escape_vias',{}).items():
    if key.startswith('U10/')or not any(t.GetNetname()==info['net']and abs(p.ToMM(t.GetPosition().x)-info['position_mm'][0])<.001 and abs(p.ToMM(t.GetPosition().y)-info['position_mm'][1])<.001 for t in valid_vias):invalid.add(key)
v['escape_vias']={key:value for key,value in v['escape_vias'].items()if key not in invalid}
v['branches']=[x for x in v['branches']if x['from'][0]+'/'+str(x['from'][1])not in invalid and x['to'][0]+'/'+str(x['to'][1])not in invalid and x['from'][0]!='U10' and x['to'][0]!='U10']
v['complete']=False;progress.write_text(json.dumps(v,indent=2)+'\n',encoding='utf8')
ctl=root/'exports/control-signal-routes.json';c=json.loads(ctl.read_text(encoding='utf8'))
c['branches']=[x for x in c['branches']if x['from'][0]!='U10'and x['to'][0]!='U10'];ctl.write_text(json.dumps(c,indent=2)+'\n',encoding='utf8')
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Mux/Q7 relocated; released local copper:',len(removed))
