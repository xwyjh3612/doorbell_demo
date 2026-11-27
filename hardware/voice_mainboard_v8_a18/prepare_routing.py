"""Prepare ground reference and explicit cutout edge clearance for routing."""
from pathlib import Path
import json,sys
import pcbnew as p
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO/'build/cad-tools/route-python'))
from shapely.geometry import Polygon,LineString
FILE=ROOT/'voice_mainboard_v8_a18.kicad_pcb';b=p.LoadBoard(str(FILE))
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
pts=data['mechanical']['outline_mm'];poly=Polygon(pts)
for a,z in zip(pts,pts[1:]+pts[:1]):
    sh=LineString([a,z]).buffer(.55,cap_style=2,join_style=2).intersection(poly)
    if sh.is_empty:continue
    shapes=[sh] if sh.geom_type=='Polygon' else [g for g in sh.geoms if g.geom_type=='Polygon']
    for piece in shapes:
        zone=p.ZONE(b);zone.SetIsRuleArea(True);zone.SetLayerSet(p.LSET.AllCuMask())
        zone.SetDoNotAllowTracks(True);zone.SetDoNotAllowVias(True);zone.SetDoNotAllowCopperPour(True)
        zone.Outline().NewOutline()
        for x,y in list(piece.exterior.coords)[:-1]:zone.Outline().Append(p.FromMM(x),p.FromMM(y))
        b.Add(zone)
for layer in [p.F_Cu,p.B_Cu]:
    zone=p.ZONE(b);zone.SetLayer(layer);zone.SetNet(b.FindNet('GND'));zone.SetLocalClearance(p.FromMM(.2))
    zone.SetMinThickness(p.FromMM(.25));zone.SetPadConnection(p.ZONE_CONNECTION_THERMAL)
    zone.SetThermalReliefGap(p.FromMM(.25));zone.SetThermalReliefSpokeWidth(p.FromMM(.3))
    zone.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS);zone.Outline().NewOutline()
    for x,y in pts:zone.Outline().Append(p.FromMM(x),p.FromMM(y))
    b.Add(zone)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
assert p.ExportSpecctraDSN(b,str(ROOT/'exports/with-ground.dsn'))
print('Prepared ground reference and explicit 0.55mm edge/cutout routing keepouts')
