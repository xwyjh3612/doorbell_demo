"""Rebuild the shell candidate with KiCad 9's bundled Python; leave V7 untouched."""
from pathlib import Path
import hashlib
import json
import math
import shutil

import pcbnew as p


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'voice_mainboard_v7'
NAME = HERE.name
BASE_PCB = BASE / 'voice_mainboard_v7.kicad_pcb'
PCB = HERE / f'{NAME}.kicad_pcb'
OUT = HERE / 'review'

# Coordinates in mm, front view through the grille; origin = upper left screw post.
OX, OY = 7.0, -7.0
HOLES = ((0, 0), (109, 0), (0, 109), (109, 109))
SPEAKER = (54.5, 87.5, 33.0)   # Drawing feature, not the flange diameter.
BATTERY = (9., 70.5, 100., 118.5)  # Position inferred from rear view.
TOP_NPTH = 4.0                  # Check against real bosses before ordering.
EAR_R = 4.2
FILLET = 1.0


def v(x, y):
    return p.VECTOR2I(p.FromMM(x), p.FromMM(y))


def coords(q):
    return (p.ToMM(q.x), p.ToMM(q.y))


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ear_edges():
    """Return outline primitives (start/end or start/mid/end), in PCB coordinates."""
    r, f = EAR_R, FILLET
    d = f / math.sqrt(2)
    y = -OY
    # Outline of the left edge, from top to bottom. A pair of inner fillets
    # avoids sharp reentrant corners at the root of the extension.
    def side(lx):
        return [((0, 0), (0, y-r-f)),
                ((0, y-r-f), (-f+d, y-r-f+d), (-f, y-r)),
                ((-f, y-r), (lx, y-r)),
                ((lx, y-r), (lx-r, y), (lx, y+r)),
                ((lx, y+r), (-f, y+r)),
                ((-f, y+r), (-f+d, y+r+f-d), (0, y+r+f)),
                ((0, y+r+f), (0, 75))]
    right = [tuple((100-x, y) for x, y in seg) for seg in side(100+OX-109)]
    return side(-OX) + [((0, 75), (100, 75))] + right + [((100, 0), (0, 0))]


def clone_project():
    for name in ('fp-lib-table', 'sym-lib-table', 'VoiceV2.kicad_sym'):
        shutil.copyfile(BASE / name, HERE / name)
    shutil.copytree(BASE / 'VoiceV2.pretty', HERE / 'VoiceV2.pretty', dirs_exist_ok=True)
    for suffix in ('pro', 'dru', 'sch'):
        shutil.copyfile(BASE / f'voice_mainboard_v7.kicad_{suffix}',
                        HERE / f'{NAME}.kicad_{suffix}')


def add_holes(board):
    # Distinct project footprint keeps library parity and excludes the holes from
    # the BOM and placement output. All four V7 holes remain where they were.
    lib = HERE / 'VoiceV2.pretty'
    fp_name = 'Shell_Post_NPTH_4mm'
    fp = p.FootprintLoad(str(lib), 'V6_BOARD_H1')
    fp.SetValue(fp_name)
    fp.SetAttributes(p.FP_BOARD_ONLY | p.FP_EXCLUDE_FROM_POS_FILES | p.FP_EXCLUDE_FROM_BOM)
    fp.SetLibDescription('Shell post, provisional 4 mm unplated drill; no component')
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    for g in tuple(fp.GraphicalItems()):
        fp.Remove(g)
    for pad in fp.Pads():
        pad.SetSize(v(TOP_NPTH, TOP_NPTH))
        pad.SetDrillSize(v(TOP_NPTH, TOP_NPTH))
    fp.SetFPIDAsString(fp_name)
    p.FootprintSave(str(lib), fp)
    for ref, (x, y) in zip(('H5', 'H6'), HOLES):
        fp = p.FootprintLoad(str(lib), fp_name)
        fp.SetFPIDAsString('VoiceV2:' + fp_name)
        fp.SetReference(ref)
        fp.SetPosition(v(x-OX, y-OY))
        fp.FixUuids()
        board.Add(fp)


def verify_preserved():
    old = p.LoadBoard(str(BASE_PCB))
    new = p.LoadBoard(str(PCB))
    def fingerprints(b, original):
        # KiCad's own serializer includes all pad geometry, links, traces/vias,
        # rule areas and actual filled-zone polygons, including net assignments.
        plugin = p.PCB_IO_KICAD_SEXPR()
        items = [*b.GetTracks(), *b.Zones(), *b.GetFootprints()]
        return {str(i.m_Uuid.AsString()): str(plugin.Format(i)) for i in items
                if not isinstance(i, p.FOOTPRINT) or i.GetReference() in original}
    refs = {f.GetReference() for f in old.GetFootprints()}
    assert fingerprints(old, refs) == fingerprints(new, refs), 'Electrical CAD objects changed'
    assert old.GetCopperLayerCount() == new.GetCopperLayerCount() == 2
    assert file_hash(BASE / 'voice_mainboard_v7.kicad_sch') == file_hash(HERE / f'{NAME}.kicad_sch')
    extra = {f.GetReference(): f for f in new.GetFootprints() if f.GetReference() not in refs}
    assert set(extra) == {'H5', 'H6'}
    for ref, (x, y) in zip(('H5', 'H6'), HOLES):
        fp = extra[ref]
        assert fp.GetPosition() == v(x-OX, y-OY)
        pad, = tuple(fp.Pads())
        assert pad.GetDrillSize() == v(TOP_NPTH, TOP_NPTH) and pad.GetAttribute() == p.PAD_ATTRIB_NPTH
    OUT.mkdir(exist_ok=True)
    evidence = dict(base_sha256=file_hash(BASE_PCB), candidate_sha256=file_hash(PCB),
                    schematic_sha256=file_hash(HERE / f'{NAME}.kicad_sch'),
                    preserved_footprints=len(refs), preserved_trace_objects=len(old.GetTracks()),
                    preserved_zones=len(old.Zones()), added_npth=['H5', 'H6'], copper_layers=2)
    (OUT / 'electrical-comparison.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(evidence, indent=2))


def main():
    clone_project()
    board = p.LoadBoard(str(BASE_PCB))
    old_edges = [d for d in board.GetDrawings() if d.GetLayer() == p.Edge_Cuts]
    assert len(old_edges) == 4
    assert {coords(q) for d in old_edges for q in (d.GetStart(), d.GetEnd())} == {
        (0, 0), (100, 0), (100, 75), (0, 75)}
    for drawing in old_edges:
        board.Remove(drawing)
    for seg in ear_edges():
        shape = p.PCB_SHAPE(board)
        shape.SetLayer(p.Edge_Cuts)
        shape.SetWidth(p.FromMM(0.05))
        if len(seg) == 3:
            shape.SetShape(p.SHAPE_T_ARC)
            shape.SetArcGeometry(*(v(*point) for point in seg))
        else:
            shape.SetShape(p.SHAPE_T_SEGMENT)
            shape.SetStart(v(*seg[0]))
            shape.SetEnd(v(*seg[1]))
        board.Add(shape)
    add_holes(board)
    assert p.SaveBoard(str(PCB), board)
    verify_preserved()


if __name__ == '__main__':
    main()
