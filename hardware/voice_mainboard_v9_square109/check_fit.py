"""Read the real KiCad PCB outline and make a 1:1 review drawing (not a shell CAD)."""
import json
import math
import re

import pcbnew as p

from build_candidate import BATTERY, HOLES, OUT, OX, OY, PCB, SPEAKER, TOP_NPTH, coords, file_hash


SHELL = (-11.5, -13., 120.5, 120.5, 25.)   # Reference outline estimated from the listing.
BUTTONS = ((12.5, 21.5), (54.5, 21.5), (96.5, 21.5))
SUPPORTS = (((11, 64), (1, 65), (0, 109)), ((103, 64), (108, 65), (109, 109)))
SUPPORT_R = 4.2
EXTRA_RADIAL_SPACE = 1.5  # Design allowance in front projection, not measured.


def shell_xy(q):
    x, y = coords(q)
    return round(x+OX, 6), round(y+OY, 6)


def signed_distance_to_shell(q):
    l, t, r, b, radius = SHELL
    x, y = q
    a = abs(x-(l+r)/2) - ((r-l)/2-radius)
    c = abs(y-(t+b)/2) - ((b-t)/2-radius)
    return math.hypot(max(a, 0), max(c, 0))+min(max(a, c), 0)-radius


def rect_dist(q, rect):
    x, y = q
    l, t, r, b = rect
    return math.hypot(max(l-x, 0, x-r), max(t-y, 0, y-b))


def chains(b):
    edges = []
    for s in b.GetDrawings():
        if s.GetLayer() != p.Edge_Cuts:
            continue
        a, e = shell_xy(s.GetStart()), shell_xy(s.GetEnd())
        edges.append((a, shell_xy(s.GetArcMid()), e) if s.GetShape() == p.SHAPE_T_ARC else (a, e))
    origin = (OX, OY)
    q = origin
    chain = []
    while edges:
        i = next(i for i, edge in enumerate(edges) if q in (edge[0], edge[-1]))
        item = edges.pop(i)
        edge = item if item[0] == q else item[::-1]
        chain.append(edge)
        q = edge[-1]
    assert q == origin
    return chain


def arc_data(seg):
    x, y = seg[0]
    bx, by = seg[1][0]-x, seg[1][1]-y
    cx, cy = seg[2][0]-x, seg[2][1]-y
    det = 2*(bx*cy-by*cx)
    ux = (cy*(bx*bx+by*by)-by*(cx*cx+cy*cy))/det
    uy = (bx*(cx*cx+cy*cy)-cx*(bx*bx+by*by))/det
    start = math.atan2(-uy, -ux)
    end = math.atan2(cy-uy, cx-ux)
    span = (end-start) % math.tau if det > 0 else -((start-end) % math.tau)
    return (x+ux, y+uy), math.hypot(ux, uy), start, span


def outline_as_svg(chain):
    path = ['M %g %g' % chain[0][0]]
    pts = []
    for seg in chain:
        if len(seg) == 3:
            center, radius, start, span = arc_data(seg)
            path.append('A %.4f %.4f 0 %d %d %g %g' % (
                radius, radius, int(abs(span)>math.pi+1e-4), int(span>0), *seg[-1]))
            pts.extend((center[0]+radius*math.cos(start+span*i/60),
                        center[1]+radius*math.sin(start+span*i/60)) for i in range(61))
        else:
            a, z = seg
            path.append('L %g %g' % z)
            pts.extend((a[0]+(z[0]-a[0])*i/60, a[1]+(z[1]-a[1])*i/60) for i in range(61))
    return ' '.join(path)+' Z', pts


def support_samples():
    for c in SUPPORTS:
        for a, b in zip(c, c[1:]):
            for j in range(101):
                yield tuple(a[i]+(b[i]-a[i])*j/100 for i in range(2))


def check(b, outline_pts):
    nominal_r = SPEAKER[2]
    d = SPEAKER[1] - (OY + 75)
    rail_pts = tuple(support_samples())
    data = dict(
        pcb_sha256=file_hash(PCB), status='listing-drawing XY only; no verified Z stack or physical fit',
        pcb_origin_mm=[OX, OY], pcb_thickness_mm=p.ToMM(b.GetDesignSettings().GetBoardThickness()),
        outline_size_mm=[round(max(q[i] for q in outline_pts)-min(q[i] for q in outline_pts), 2) for i in range(2)],
        inferred_outer_profile_mm=SHELL,
        pcb_to_reference_outline_mm=round(-max(map(signed_distance_to_shell, outline_pts)), 2),
        projected_speaker_circle_mm=SPEAKER,
        speaker_projection_into_board_mm=round(nominal_r-d, 2),
        speaker_projection_chord_at_board_edge_mm=round(2*math.sqrt(nominal_r**2-d**2), 2),
        concentric_magnet_diameter_clear_with_1p5mm_radial_margin_mm=round(2*(d-EXTRA_RADIAL_SPACE), 2),
        board_to_projected_battery_mm=round(BATTERY[1]-(OY+75), 2),
        support_to_reference_outline_mm=round(-max(map(signed_distance_to_shell, rail_pts))-SUPPORT_R, 2),
        support_to_projected_battery_mm=round(min(rect_dist(q, BATTERY) for q in rail_pts)-SUPPORT_R, 2),
        support_to_projected_speaker_mm=round(min(math.dist(q, SPEAKER[:2]) for q in rail_pts)-SUPPORT_R-nominal_r, 2),
        buttons_mm=BUTTONS, mounting_centres_mm=HOLES,
    )
    boxes = {}
    for f in b.GetFootprints():
        rect = f.GetBoundingBox(False, False)
        ref = f.GetReference()
        if not ref.startswith(('H', 'TP')):
            boxes[ref] = (*shell_xy(rect.GetOrigin()), *shell_xy(rect.GetEnd()))
    data['projected_speaker_region_check_footprints'] = sorted(
        ref for ref, r in boxes.items() if rect_dist(SPEAKER[:2], r)<nominal_r+EXTRA_RADIAL_SPACE)
    data['button_stem_clearance_check_footprints'] = [sorted(
        ref for ref, r in boxes.items() if rect_dist(btn, r)<5) for btn in BUTTONS]
    data['bracket_near_THT_pads'] = []
    for f in b.GetFootprints():
        for pad in f.Pads():
            if pad.GetAttribute() == p.PAD_ATTRIB_PTH:
                rect = pad.GetBoundingBox()
                r = (*shell_xy(rect.GetOrigin()), *shell_xy(rect.GetEnd()))
                if min(rect_dist(q, r) for q in rail_pts) < SUPPORT_R:
                    data['bracket_near_THT_pads'].append(f'{f.GetReference()}:{pad.GetNumber()}')
    assert data['pcb_to_reference_outline_mm'] > 0, data
    assert data['support_to_projected_battery_mm'] > 0, data
    assert data['support_to_reference_outline_mm'] > 0, data
    assert data['support_to_projected_speaker_mm'] > 0, data
    assert not data['bracket_near_THT_pads'], data
    (OUT/'fit-check.json').write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    return data


def svg(b, path, data):
    l, t, r, bot, radius = SHELL
    bl, bt, br, bb = BATTERY
    x, y, rad = SPEAKER
    chord = data['speaker_projection_chord_at_board_edge_mm']/2
    board_bottom = OY+75
    cap_path = f'M {x-chord} {board_bottom} A {rad} {rad} 0 0 1 {x+chord} {board_bottom} Z'
    page = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="190mm" height="193mm" viewBox="-38 -31 190 193">
<rect x="-38" y="-31" width="190" height="193" fill="white"/>
<text x="-32" y="-23" class="em">Voice intercom · V9 / Square 109 fit check</text>
<text x="-32" y="-17.5">Print at actual size (100%). View: from the front grille toward the PCB.</text>
<rect x="{l}" y="{t}" width="{r-l}" height="{bot-t}" rx="{radius}" fill="#f6f8fa" stroke="#74909d" stroke-width=".32" stroke-dasharray="1.5 1"/>
<path d="{path}" fill="#dceee2" stroke="#195e49" stroke-width=".4"/>
<rect x="{bl}" y="{bt}" width="{br-bl}" height="{bb-bt}" rx="1.5" fill="#e6edf9" stroke="#456da6" stroke-width=".35" stroke-dasharray="2 1"/>
<circle cx="{x}" cy="{y}" r="{rad}" fill="none" stroke="#c3581c" stroke-width=".45"/>
<path d="{cap_path}" fill="#f8d4af" stroke="#c3581c" stroke-width=".24"/>
<circle cx="{x}" cy="{y}" r="{data['concentric_magnet_diameter_clear_with_1p5mm_radial_margin_mm']/2}" fill="none" stroke="#c3581c" stroke-width=".23" stroke-dasharray="1.4 1"/>
<path d="M 51.5 87.5 h 6 m -3 -3 v 6" fill="none" stroke="#c3581c" stroke-width=".23"/>
<text x="54.5" y="97.5" text-anchor="middle">Speaker region Ø66 (shell drawing)</text>
<text x="54.5" y="103" class="small" text-anchor="middle">Dashed inner circle: Ø36 magnet with 1.5 mm radial clearance</text>
<text x="54.5" y="115.5" class="small" text-anchor="middle">Battery envelope · rear half · 91 × 48 × 6 mm</text>
<path d="M 0 1 V -10 M 109 1 V -10 M 0 -9 H 109 M 0 109 H -21 M 0 0 H -21 M -20 0 V 109" fill="none" stroke="#506570" stroke-width=".23" stroke-dasharray="1.7 .8"/>
<text x="54.5" y="-10" text-anchor="middle" class="dim">109 mm between post centres</text>
<text x="-21.5" y="54.5" text-anchor="middle" transform="rotate(-90 -21.5 54.5)" class="dim">109 mm between post centres</text>''']
    for c in SUPPORTS:
        points = ' '.join('%g,%g' % q for q in c)
        page.append(f'<polyline points="{points}" fill="none" stroke="#7c68ad" stroke-opacity=".43" stroke-width="{2*SUPPORT_R}" stroke-linecap="round" stroke-linejoin="round"/>')
    for n, (cx, cy) in enumerate(HOLES):
        page.append(f'<circle cx="{cx}" cy="{cy}" r="{TOP_NPTH/2}" fill="white" stroke="#40346a" stroke-width=".32"/>')
        page.append(f'<path d="M {cx-3.1} {cy} h 6.2 m -3.1 -3.1 v 6.2" fill="none" stroke="#40346a" stroke-width=".2"/>')
        if n<2:
            page.append(f'<text x="{cx}" y="{-5.3}" text-anchor="middle" class="small">H{n+5} Ø4</text>')
    for f in b.GetFootprints():
        ref = f.GetReference()
        cx, cy = shell_xy(f.GetPosition())
        if ref in ('H1','H2','H3','H4'):
            page.append(f'<circle cx="{cx}" cy="{cy}" r="1.6" fill="white" stroke="#195e49" stroke-width=".26"/>')
            if ref in ('H3','H4'):
                page.append(f'<text x="{cx}" y="{cy+5.5}" text-anchor="middle" class="small">{ref}</text>')
        labels = {'J1': ('5 V IN (J1)', 3, 4), 'J17': ('CALL (J17)', 0, 5.5),
                  'J18': ('TTL (J18)', 0, 5.5), 'J15': ('SPK (J15)', -1, 4.5),
                  'J14': ('MIC (J14)', -1, 4.5), 'J23': ('BAT (J23)', 3, -4),
                  'J16': ('RADAR (J16)', -1, -2), 'J11': ('LTE antenna', 0, -4),
                  'U7': ('ESP32-S3', 0, 3.5), 'U1': ('ML307C-DL', 0, -5)}
        if ref in labels:
            title, dx, dy = labels[ref]
            page.append(f'<circle cx="{cx}" cy="{cy}" r=".77" fill="#195e49"/><text x="{cx+dx}" y="{cy+dy}" text-anchor="middle" class="small">{title}</text>')
    for i, (cx, cy) in enumerate(BUTTONS):
        page.append(f'<circle cx="{cx}" cy="{cy}" r="2.8" fill="white" fill-opacity=".85" stroke="#805c2b" stroke-width=".32" stroke-dasharray="1 .55"/><text x="{cx}" y="{cy+1}" class="small" text-anchor="middle">{i+1}</text>')
    page.append('''<text x="54.5" y="50" text-anchor="middle">100 × 75 mm board body · two new top mounting ears</text>
<rect x="-27" y="126" width="6" height="3.1" fill="#dceee2" stroke="#195e49" stroke-width=".26"/><text x="-18" y="128.7">PCB</text>
<rect x="4" y="126" width="6" height="3.1" fill="#c0b5d8"/><text x="13" y="128.7">Rear brackets</text>
<rect x="49" y="126" width="6" height="3.1" fill="#f8d4af" stroke="#c3581c" stroke-width=".24"/><text x="58" y="128.7">Speaker overlaps PCB in XY</text>
<circle cx="111.5" cy="127.4" r="1.5" fill="white" stroke="#805c2b" stroke-width=".25"/><text x="116" y="128.7">Button stems</text>
<path d="M -27 145 V 140 H 73 V 145 M -17 140 v 3 m 10 -3 v 3 m 10 -3 v 3 m 10 -3 v 3 m 10 -3 v 5 m 10 -5 v 3 m 10 -3 v 3 m 10 -3 v 3 m 10 -3 v 3" fill="none" stroke="#172b39" stroke-width=".3"/>
<text x="-27" y="150" class="small">0</text><text x="23" y="150" class="small" text-anchor="middle">50</text><text x="73" y="150" class="small" text-anchor="end">100 mm</text>
<text x="-27" y="157">Check ruler before using. Confirm shell ribs, screw sizes and all height clearances with actual parts.</text>
</svg>''')
    def text_style(match):
        attrs = match[1]
        cls = re.search(r' class="(\w+)"', attrs)
        size = {'dim': 2.9, 'em': 4.3, 'small': 2.65}.get(cls[1] if cls else '', 3.1)
        weight = ' font-weight="bold"' if cls and cls[1] == 'em' else ''
        return f'<text font-family="Arial,sans-serif" fill="#172b39" font-size="{size}"{weight}{attrs}>'
    svg_source = re.sub(r'<text([^>]*)>', text_style, '\n'.join(page))
    (OUT/'fit-template.svg').write_text(svg_source+'\n', encoding='utf-8')


if __name__ == '__main__':
    board = p.LoadBoard(str(PCB))
    path, points = outline_as_svg(chains(board))
    result = check(board, points)
    svg(board, path, result)
    print(json.dumps(result, indent=2))
