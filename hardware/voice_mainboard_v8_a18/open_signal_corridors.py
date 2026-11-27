"""Trial removal of discrete ground wires outside local power and RF areas."""
import json
import os
import shutil

from comparison_route_geometry import b, FILE, p, pos
from repair_comparison_groups import groups
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

assert FILE.parent.name == 'closure_ground_trial', 'Run only on the isolated routing trial'
reference = FILE.parent/'before-ground-corridors.kicad_pcb'
assert not reference.exists()
shutil.copy2(FILE, reference)
parts = {part.GetReference(): part for part in b.GetFootprints()}
radii = {'U1': 12.5, 'J11': 5, 'U2': 5, 'U13': 5, 'U15': 5, 'U16': 4,
         'U17': 3.5, 'U18': 4.5, 'U14': 3, 'J1': 5, 'C75': 4.8, 'C76': 4.8}
preserve = unary_union([Point(pos(parts[ref])).buffer(radius) for ref, radius in radii.items()])
before_groups = len(groups('GND'))
retired = []
for track in list(b.GetTracks()):
    if track.GetNetname() != 'GND' or track.IsLocked() or isinstance(track, p.PCB_VIA):
        continue
    start, end = track.GetStart(), track.GetEnd()
    shape = LineString([(p.ToMM(point.x), p.ToMM(point.y)) for point in (start, end)])
    if preserve.intersects(shape.buffer(p.ToMM(track.GetWidth())/2)):
        continue
    retired.append(track)
    b.Remove(track)
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE), b)
report = {'removed_ground_tracks': len(retired), 'ground_pad_groups_before': before_groups,
          'ground_pad_groups_after': len(groups('GND')), 'protected_neighborhood_radii_mm': radii,
          'trial_only': True, 'power_returns_require_independent_check': True}
(FILE.parent/'exports/ground-corridors.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
for track in retired:
    track.thisown = False
print(json.dumps(report, indent=2))
