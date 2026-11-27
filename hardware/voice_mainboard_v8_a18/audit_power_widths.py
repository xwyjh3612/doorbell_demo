"""Read-only review of actual rail copper; does not certify current capability.

Compare long rail segments with the routing target and expose narrow necks.
Current/temperature qualification still needs a loop review and hardware tests.
"""
import collections
import hashlib
import json
import os
from pathlib import Path

import pcbnew as p

file = Path(os.environ['A18_REPAIR_BOARD']).resolve()
b = p.LoadBoard(str(file))
rails = {
    'VIN_DC', 'VIN_FUSED', 'VIN_PROTECTED', 'SYS_5V', 'MODEM_3V8',
    'BAT_BOOST_5V', 'BAT_SENSE_IN', 'CELL_NEG', 'UPS_SW', 'BUCK_SW',
    'ESP_SW',
}
target = .5
neck_limit = 1.5
by_net = collections.defaultdict(list)
for t in b.GetTracks():
    if t.GetNetname() not in rails or isinstance(t, p.PCB_VIA):
        continue
    a, z = t.GetStart(), t.GetEnd()
    width = p.ToMM(t.GetWidth())
    length = ((a.x-z.x)**2+(a.y-z.y)**2)**.5 / 1e6
    by_net[t.GetNetname()].append({
        'uuid': t.m_Uuid.AsString(), 'width_mm': width,
        'length_mm': length, 'layer': p.LayerName(t.GetLayer()),
        'from_mm': [p.ToMM(a.x), p.ToMM(a.y)],
        'to_mm': [p.ToMM(z.x), p.ToMM(z.y)],
    })
results = []
for net in sorted(rails):
    tracks = by_net[net]
    narrow = [t for t in tracks if t['width_mm'] < target-1e-6]
    long_narrow = [t for t in narrow if t['length_mm'] > neck_limit]
    results.append({
        'net': net,
        'minimum_track_width_mm': min((t['width_mm'] for t in tracks), default=None),
        'total_track_length_mm': sum(t['length_mm'] for t in tracks),
        'below_target_length_mm': sum(t['length_mm'] for t in narrow),
        'long_narrow_segments': long_narrow,
        'neck_segments_require_combined_path_review': bool(narrow),
    })
report = {
    'PCB_sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
    'rail_routing_target_width_mm': target,
    'single_segment_neck_review_threshold_mm': neck_limit,
    'rails': results,
    'actual_2A_qualified': False,
    'scope': 'All actual track segments, including branches and stubs. Adjacent '
             'short segments can form a long neck; segment thresholds alone '
             'cannot approve a path. Does not model copper pours, thermal '
             'rise, peak duration, component limits or via current sharing.',
}
out = file.parent/'exports/power-width-audit.json'
out.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({
    'rails_checked': len(results),
    'long_narrow_segments': sum(len(t['long_narrow_segments']) for t in results),
    'actual_2A_qualified': False,
    'report': str(out),
}, indent=2))
