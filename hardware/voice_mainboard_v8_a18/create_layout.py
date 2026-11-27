"""Create an independent A18 mechanical/layout candidate from V7.

Preserve pad net assignments and the schematic. Never scale footprints or
reuse copper after moving parts. Screenshot-derived outline details remain
provisional; this is not a fabrication release.
"""
from pathlib import Path
import collections, hashlib, json, math, shutil, sys
import pcbnew as p

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / 'build/cad-tools/route-python'))
from shapely import affinity
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import polygonize, unary_union

BASE = ROOT.parent / 'voice_mainboard_v7'
ROOT.mkdir(exist_ok=True)
(ROOT / 'exports').mkdir(exist_ok=True)
for ext in ['kicad_sch', 'kicad_pro', 'kicad_dru']:
    shutil.copy2(BASE / ('voice_mainboard_v7.' + ext), ROOT / ('voice_mainboard_v8_a18.' + ext))
for name in ['VoiceV2.kicad_sym', 'fp-lib-table', 'sym-lib-table']:
    shutil.copy2(BASE / name, ROOT / name)
shutil.copytree(BASE / 'VoiceV2.pretty', ROOT / 'VoiceV2.pretty', dirs_exist_ok=True)
b = p.LoadBoard(str(BASE / 'voice_mainboard_v7.kicad_pcb'))
fps = {f.GetReference(): f for f in b.GetFootprints()}
data = json.loads((BASE / 'design.json').read_text(encoding='utf-8'))
parts = {q['ref']: q for q in data['parts']}
oldxy = {r: (p.ToMM(f.GetPosition().x), p.ToMM(f.GetPosition().y)) for r, f in fps.items()}
oldangle = {r: f.GetOrientationDegrees() for r, f in fps.items()}
padnets = lambda board: sorted((f.GetReference(), d.GetNumber(), d.GetNetname()) for f in board.GetFootprints() for d in f.Pads())
before_nets = padnets(b)
held = []
for t in list(b.GetTracks()):
    held.append(t); b.Remove(t)
for z in list(b.Zones()):
    held.append(z); b.Remove(z)
for g in list(b.GetDrawings()):
    held.append(g); b.Remove(g)

# Origin: top-left PCB outer bounding rectangle. Upper notch position/depth
# inferred from the screenshot; lower notch 36mm width is dimensioned, depth
# is provisionally taken from the 17.75mm rear-view annotation.
outline = [(0, 0), (45.39, 0), (45.39, 9.9), (52.89, 9.9),
           (52.89, 0), (73, 0), (73, 73), (54.5, 73),
           (54.5, 55.25), (18.5, 55.25), (18.5, 73), (0, 73)]
boardpoly = Polygon(outline)
inner = boardpoly.buffer(-0.5, join_style=2)
def vec(x, y): return p.VECTOR2I(p.FromMM(x), p.FromMM(y))
for a, z in zip(outline, outline[1:] + outline[:1]):
    g = p.PCB_SHAPE(b); g.SetShape(p.S_SEGMENT); g.SetLayer(p.Edge_Cuts)
    g.SetStart(vec(*a)); g.SetEnd(vec(*z)); g.SetWidth(p.FromMM(.05)); b.Add(g)

mountrefs = sorted(r for r in fps if parts.get(r, {}).get('group') == 'MECHANICAL')
assert len(mountrefs) == 4, mountrefs
mountxy = [(3.5, 3.5), (69.5, 3.5), (3.5, 69.5), (69.5, 69.5)]
for r, xy in zip(mountrefs, mountxy):
    fps[r].SetPosition(vec(*xy))
    for d in fps[r].Pads(): d.SetDrillSize(vec(3, 3)); d.SetSize(vec(3, 3))

def court(f):
    segments = []
    for g in f.GraphicalItems():
        if g.GetLayer() in [p.F_CrtYd, p.B_CrtYd] and g.GetShape() == p.S_SEGMENT:
            segments.append(LineString([(p.ToMM(g.GetStart().x), p.ToMM(g.GetStart().y)),
                                        (p.ToMM(g.GetEnd().x), p.ToMM(g.GetEnd().y))]))
    polys = list(polygonize(segments))
    if polys: return unary_union(polys)
    shapes = []
    for d in f.Pads():
        x, y = p.ToMM(d.GetPosition().x), p.ToMM(d.GetPosition().y)
        sx, sy = p.ToMM(d.GetSize().x), p.ToMM(d.GetSize().y)
        shapes.append(box(x-sx/2-.25, y-sy/2-.25, x+sx/2+.25, y+sy/2+.25))
    return unary_union(shapes)

def move(r, xy, angle):
    fps[r].SetOrientationDegrees(angle); fps[r].SetPosition(vec(*xy))

# C8 retains its exact part and value; backside placement resolves the known
# 10.5mm-vs-10mm height conflict. No unqualified capacitor is substituted.
for r,f in fps.items():
    if r=='C8' or (parts.get(r,{}).get('group')=='02 INTEGRATED UPS / POWER STATUS' and r!='J23'):
        f.Flip(f.GetPosition(), False)
targets = {
 'U7': (13,35,90), 'U1': (53,25,0), 'SW1': (36.5,36.5,0),
 'D2': (36.5,9.9,180), 'C8': (15,13,0),
 'J1': (72.5,44,180), 'J10': (36,21,0), 'J11': (65,25,0),
 'J14': (6,62,90), 'J23': (59,62,90), 'J18': (63,56,90),
 'J16': (70,16,0), 'J12': (70,30,0), 'J22': (57,52,90),
 'J15': (63,51,90), 'J17': (8,52,90), 'J8': (57,38,90),
 'SW2': (10,64,0), 'SW3': (61,65,0),
 'U2': (19,13,0), 'L1': (18.5,7.8,90),
 'C4': (14,13,90), 'C6': (24.5,7,90), 'C7': (24.5,10.2,90),
 'R2': (24.8,14.1,0), 'R3': (24.8,16.3,0), 'C37':(22.7,14.1,0),
 'U13': (23,21,180), 'L5': (23,16.5,0),
 'C60': (28,18,90), 'C59': (17.5,21,90), 'R59': (26.5,22.5,0),
 'R60': (26.5,24.5,0), 'C63': (29.2,23.5,0),
 'U14': (46,47,0), 'U16': (47,47,0), 'U15': (30,46,0),
 'L4': (24,46,0), 'U17': (13,48,0), 'U18': (52,36,0),
 'U19': (17,37,0), 'U3': (31,28,0), 'U4': (30,42,0),
 'U5': (30,49,0), 'Q6': (60,37,0), 'F1': (67,36,0), 'Q7': (56,48,0),
 'C64': (26,52,90), 'C65': (34.8,46,90), 'C66': (30,52,0),
 'C67': (47,42,0), 'C68': (47,52,0), 'C71': (47,36,90),
 'C72': (56.8,36,90), 'C73': (52,41,90),
 'R61': (35,50.5,0), 'R62': (35,52.5,0), 'R63': (30,41.5,0),
 'R64': (41.5,47,90), 'R65': (41,42,0), 'R66': (41,44.5,0),
 'D1': (43,27,0)
}
for r, (x, y, angle) in targets.items(): move(r, (x,y), angle)

bosses = [Point(*xy).buffer(3.5) for xy in mountxy] # provisional 7mm boss reserve
button_clear = box(30,30,43,43) # provisional plunger/assembly clearance
occupied = {p.F_Cu: list(bosses), p.B_Cu: list(bosses)}
# Mechanical overlap must be clear on both faces. ESP antenna keepout also
# applies to backside copper and backside parts.
espkeep = []
for z in fps['U7'].Zones():
    for i in range(z.Outline().OutlineCount()):
        ch = z.Outline().COutline(i)
        espkeep.append(Polygon([(p.ToMM(ch.CPoint(j).x),p.ToMM(ch.CPoint(j).y)) for j in range(ch.PointCount())]))
antenna = unary_union(espkeep)
occupied[p.B_Cu].append(antenna.intersection(boardpoly))
placements = []
def allowed(r, sh, layer):
    check = sh.intersection(boardpoly) if r == 'U7' else sh
    if not inner.buffer(.01).covers(check):
        # Standard ESP antenna courtyard extends into free space outside PCB.
        if r != 'U7' or not boardpoly.buffer(.001).covers(check): return False
    if layer==p.F_Cu and r not in ['U7','SW1'] and sh.intersects(button_clear): return False
    return not any(sh.intersection(o).area > 1e-7 for o in occupied[layer])

def place(r, fixed=False):
    f = fps[r]; layer = p.F_Cu if f.GetLayer() == p.F_Cu else p.B_Cu
    xy = (p.ToMM(f.GetPosition().x),p.ToMM(f.GetPosition().y)); a = f.GetOrientationDegrees()
    sh = court(f)
    if not fixed and not allowed(r,sh,layer):
        # Find a legal position near its assigned functional cluster. Pads and
        # courtyard shapes never scale; rotation is limited to 90-degree steps.
        cx,cy = xy
        local = affinity.translate(sh, -cx, -cy)
        choices = []
        for delta in [0,90,180,270]:
            rotated = affinity.rotate(local,-delta,origin=(0,0))
            for radius in range(0,161):
                span = radius*.25
                # Search square rings, nearest candidates first.
                offsets = [(dx*.25,dy*.25) for dx in range(-radius,radius+1)
                           for dy in ([-radius,radius] if radius else [0])]
                if radius: offsets += [(dx*.25,dy*.25) for dy in range(-radius+1,radius) for dx in [-radius,radius]]
                found = None
                for dx,dy in sorted(offsets,key=lambda q:q[0]*q[0]+q[1]*q[1]):
                    tx,ty = cx+dx,cy+dy
                    cand = affinity.translate(rotated,tx,ty)
                    if allowed(r,cand,layer): found=(tx,ty,a+delta,cand); break
                if found:
                    choices.append((math.hypot(found[0]-cx,found[1]-cy)+(.2 if delta else 0),found));break
            if choices and choices[-1][0] < .51: break
        if not choices: raise RuntimeError('No legal placement for '+r)
        _,(x,y,a,sh)=min(choices,key=lambda q:q[0]);move(r,(x,y),a);xy=(x,y)
    if not allowed(r,sh,layer): raise RuntimeError('Fixed mechanical conflict for '+r)
    occupied[layer].append(sh.buffer(.08,join_style=2))
    placements.append({'ref':r,'x':xy[0],'y':xy[1],'angle':a,'side':'F' if layer==p.F_Cu else 'B','courtyardArea':sh.area})
    print('Placed',r,tuple(round(v,2)for v in xy),flush=True)

for r in ['U7','SW1','D2','C8']: place(r,True)
for r in ['J1','J10','U1','J11','L1','L4','U16','U15','U13','U2','L5','U14','U18','U17','U19',
          'J14','J23','J18','J16','J12','J22','J15','J17','SW2','SW3','J8','F1','Q6','U3','U4','U5','Q7','D1']:
    place(r)
for r in targets:
    if not any(q['ref']==r for q in placements):place(r)

anchors=[r for r in targets if r.startswith(('U','L','Q','F','D','J')) and r!='U7']
remaining=[r for r in fps if r not in targets and r not in mountrefs]
# Prefer the closest connected IC in the original placement to keep local
# converter feedback/decoupling parts together; each cluster is rotated with
# its anchor. Every result still needs routing/loop review.
fp_nets={r:{d.GetNetname() for d in f.Pads() if d.GetNetname() not in ['', 'GND','ESP_3V3','SYS_5V','VIN_PROTECTED','MODEM_3V8','BAT_SENSE_IN']} for r,f in fps.items()}
for r in remaining:
    pool=[a for a in anchors if fp_nets[r]&fp_nets[a]] or anchors
    anchor=min(pool,key=lambda a:math.dist(oldxy[r],oldxy[a]))
    ax,ay=p.ToMM(fps[anchor].GetPosition().x),p.ToMM(fps[anchor].GetPosition().y)
    delta=fps[anchor].GetOrientationDegrees()-oldangle[anchor];rad=math.radians(-delta)
    dx,dy=oldxy[r][0]-oldxy[anchor][0],oldxy[r][1]-oldxy[anchor][1]
    tx=ax+dx*math.cos(rad)-dy*math.sin(rad);ty=ay+dx*math.sin(rad)+dy*math.cos(rad)
    move(r,(max(7,min(69,tx)),max(5,min(67,ty))),oldangle[r]+delta)
remaining.sort(key=lambda r:court(fps[r]).area,reverse=True)
for r in remaining: place(r)

# Physical boundaries for the boss and central button are visible and also
# become routing keepouts. The central switch pads must remain routable.
for sh in bosses:
    z=p.ZONE(b);z.SetLayerSet(p.LSET.AllCuMask());z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True);z.SetDoNotAllowCopperPour(True);z.SetDoNotAllowPads(True)
    z.Outline().NewOutline()
    for x,y in list(sh.exterior.coords)[:-1]:z.Outline().Append(p.FromMM(x),p.FromMM(y))
    b.Add(z)
for sh in [button_clear,box(18.5,55.25,54.5,73)]:
    pts=list(sh.exterior.coords)
    for a,z in zip(pts,pts[1:]):
        g=p.PCB_SHAPE(b);g.SetShape(p.S_SEGMENT);g.SetLayer(p.Dwgs_User);g.SetStart(vec(*a));g.SetEnd(vec(*z));g.SetWidth(p.FromMM(.15));b.Add(g)

for r,f in fps.items():
    if r in parts:
        parts[r].update(x=p.ToMM(f.GetPosition().x),y=p.ToMM(f.GetPosition().y),angle=f.GetOrientationDegrees(),side='F' if f.GetLayer()==p.F_Cu else 'B')
    f.Reference().SetVisible(False);f.Value().SetVisible(False)
assert padnets(b)==before_nets, 'Pad net assignments changed'
b.BuildConnectivity()
file=ROOT/'voice_mainboard_v8_a18.kicad_pcb';p.SaveBoard(str(file),b)
assert p.ExportSpecctraDSN(b,str(ROOT/'exports/placement.dsn'))
data.update(revision='V8-A18-PLACEMENT-CANDIDATE',dimensions_mm=[73,73],layers=2,smt_sides=2,
            status='A18 SCREENSHOT-DERIVED MECHANICAL AND PLACEMENT CANDIDATE; NOT ROUTED OR RELEASED',
            parts=list(parts.values()),manufacturing_ready=False,firmware_modified=False)
data['mechanical']={'enclosure':'A18 85x85x31mm','outline_mm':outline,'mount_holes_mm':mountxy,
                   'mount_drill_mm':3,'provisional_boss_diameter_mm':7,'front_height_mm':10,'back_height_mm':15,
                   'button_xy_mm':[36.5,36.5],'lightguide_xy_mm':[36.5,9.9],'battery_notch_width_mm':36,
                   'unverified_dimensions':['upper-notch exact x/depth','lower-notch exact depth','boss outer diameter',
                   'button stroke/height','light-guide exact position/height','cell compartment inner size','speaker/microphone and cable envelopes'],
                   'C8_side':'B; same 10.5mm part, below nominal backside15mm limit','enclosure_fit_verified':False}
data['parent_PCB_sha256']=hashlib.sha256((BASE/'voice_mainboard_v7.kicad_pcb').read_bytes()).hexdigest()
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(ROOT/'exports/placement-validation.json').write_text(json.dumps({'PCB_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
 'pad_net_assignments_unchanged':True,'footprint_count':len(fps),'board_polygon_area_mm2':boardpoly.area,
 'placements':placements,'all_candidate_courtyards_inside_or_ESP_antenna_outside':True,
 'courtyard_overlap_with_selected_reserves':False,'mechanical_dimensions_provisional':True,
 'native_DRC_run':False,'full_board_simulated':False,'manufacturing_ready':False},ensure_ascii=False,indent=2),encoding='utf-8')
for t in held:t.thisown=False
print('Saved A18 independent placement candidate; routing/DRC/physical fit pending',flush=True)
