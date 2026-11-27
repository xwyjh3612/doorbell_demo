"""Resolve native placement findings before routing the A18 candidate."""
from pathlib import Path
import json, math, sys
import pcbnew as p
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO/'build/cad-tools/route-python'))
from shapely.geometry import LineString,Point,Polygon,box
from shapely.ops import polygonize,unary_union
FILE=ROOT/'voice_mainboard_v8_a18.kicad_pcb';b=p.LoadBoard(str(FILE))
fps={f.GetReference():f for f in b.GetFootprints()}
def xy(point):return (p.ToMM(point.x),p.ToMM(point.y))
def court(f):
    lines=[];others=[]
    for g in f.GraphicalItems():
        if g.GetLayer() not in [p.F_CrtYd,p.B_CrtYd]:continue
        if g.GetShape()==p.S_SEGMENT:lines.append(LineString([xy(g.GetStart()),xy(g.GetEnd())]))
        elif g.GetShape()==p.S_CIRCLE:others.append(Point(*xy(g.GetStart())).buffer(math.dist(xy(g.GetStart()),xy(g.GetEnd()))+.025))
    return unary_union([*polygonize(lines),*others])
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
poly=Polygon(data['mechanical']['outline_mm']).buffer(-.6,join_style=2)
button=box(30,30,43,43)
occupied={p.F_Cu:[],p.B_Cu:[]}
for r,f in fps.items():
    if not r.startswith('TP'):occupied[f.GetLayer()].append(court(f).buffer(.1,join_style=2))
for r in sorted(r for r in fps if r.startswith('TP')):
    f=fps[r];layer=f.GetLayer();old=xy(f.GetPosition())
    found=None
    # Test-point courtyard is a circle, not the pad-only bounding rectangle.
    for x,y in sorted(((x*.5,y*.5)for x in range(3,143)for y in range(3,143)),key=lambda z:math.dist(old,z)):
        f.SetPosition(p.VECTOR2I(p.FromMM(x),p.FromMM(y)));sh=court(f)
        if not poly.covers(sh) or sh.intersects(button):continue
        if any(sh.intersects(o)for o in occupied[layer]):continue
        found=(x,y);occupied[layer].append(sh.buffer(.1));break
    if found is None:raise RuntimeError('No testpoint placement '+r)

# NPTH holes are allowed in their own boss clearance; only copper is banned.
for z in b.Zones():
    if z.GetIsRuleArea() and z.GetDoNotAllowPads():z.SetDoNotAllowPads(False)

# Use an explicit 3mm mounting-hole library so DRC compares the real design
# rather than reporting a modified standard 3.2mm hole.
io=p.PCB_IO_KICAD_SEXPR()
for r in ['H1','H2','H3','H4']:
    f=fps[r];f.SetFPID(p.LIB_ID('VoiceV2','A18_MountingHole_3mm_7mmReserve'))
    clone=f.Duplicate();clone.SetPosition(p.VECTOR2I(0,0));clone.SetOrientationDegrees(0)
    clone.SetReference('REF**');clone.SetValue('MountingHole_3mm')
    io.FootprintSave(str(ROOT/'VoiceV2.pretty'),clone)
text=(ROOT/'voice_mainboard_v8_a18.kicad_sch').read_text(encoding='utf-8')
text=text.replace('MountingHole:MountingHole_3.2mm_M3','VoiceV2:A18_MountingHole_3mm_7mmReserve')
(ROOT/'voice_mainboard_v8_a18.kicad_sch').write_text(text,encoding='utf-8')

# SetValue changed the Reference field in this SWIG build when R64/R66's
# field ordering was inherited. Set both named fields explicitly.
for r in ['R64','R66']:
    f=fps[r];f.Reference().SetText(r);f.Value().SetText('12k 1%'if r=='R64'else'200k 1%')

for q in data['parts']:
    f=fps[q['ref']];q.update(x=xy(f.GetPosition())[0],y=xy(f.GetPosition())[1],angle=f.GetOrientationDegrees())
    if q['ref'].startswith('H'):q['footprint']='VoiceV2:A18_MountingHole_3mm_7mmReserve'
p.SaveBoard(str(FILE),b)
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Refined circular testpoint courtyards, mounting-hole library and field references')
