"""Remove only exact same-net, same-geometry duplicate copper objects."""
import json
from comparison_route_geometry import b, FILE, p

seen, removed = {}, []
for t in list(b.GetTracks()):
    if isinstance(t, p.PCB_VIA):
        key = ('via', t.GetNetname(), t.GetPosition().x, t.GetPosition().y,
               t.GetWidth(p.F_Cu), t.GetDrill(), t.GetViaType())
    else:
        ends = sorted([(t.GetStart().x, t.GetStart().y),
                       (t.GetEnd().x, t.GetEnd().y)])
        key = ('track', t.GetNetname(), t.GetLayer(), t.GetWidth(), *ends)
    if key in seen:
        seen[key].SetLocked(seen[key].IsLocked() or t.IsLocked())
        removed.append(t)
        b.Remove(t)
    else:
        seen[key] = t
report = [{'uuid': t.m_Uuid.AsString(), 'net': t.GetNetname(),
           'via': isinstance(t, p.PCB_VIA)} for t in removed]
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE), b)
for t in removed:
    t.thisown = False
(FILE.parent/'exports/exact-duplicate-copper.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('Removed exact same-net copper duplicates:', len(removed))
