"""Record the C-DL-specific public library, without treating it as a HW manual.

Input is the downloaded EasyEDA product API response. Coordinates are converted
from EasyEDA's 0.254 mm units; each pad polygon is checked independently.
Source: JLCEDA/EasyEDA Official Library https://lceda.cn/ https://easyeda.com
The library's attribution statement is preserved in the source record.
"""
from pathlib import Path
import json, hashlib, re
import pcbnew as p

ROOT = Path(__file__).resolve().parent
API = Path('build/v4-reference/c-discovery-1.txt')
raw = API.read_bytes()
record = json.loads(raw.decode('utf-8-sig'))
assert record['success']
source = record['result']
assert source['title'] == 'ML307C-DL'
assert source['lcsc']['number'] == 'C48972417'
symbol, package = source['dataStr'], source['packageDetail']['dataStr']
names = {}
for shape in symbol['shape']:
    if not shape.startswith('P~'):
        continue
    sections = shape.split('^^')
    number, name = sections[0].split('~')[3], sections[3].split('~')[4]
    assert number not in names
    names[number] = name
assert set(names) == {str(n) for n in range(1, 110)}
assert all(names[str(n)] == name for n, name in {
    7: 'PWR_ON/OFF', 11: 'USIM0_DATA', 12: 'USIM0_RESET',
    13: 'USIM0_CLK', 14: 'USIM0_PWR', 15: 'RESET', 17: 'UART0_RXD',
    18: 'UART0_TXD', 19: 'UART0_DTR', 24: 'VDD_EXT', 35: 'ANT_MAIN',
    42: 'VBAT', 43: 'VBAT', 59: 'USB_DP', 60: 'USB_DM', 61: 'USB_VBUS',
    77: 'USIM1_DET', 79: 'USIM0_DET', 82: 'BOOT_MODE'}.items())

fp = p.FOOTPRINT(None)
fp.SetFPID(p.LIB_ID('VoiceV2', 'ML307C_DL_109_LIBRARY_REVIEW'))
fp.SetAttributes(p.FP_SMD)
fp.SetLibDescription('JLCEDA/EasyEDA Official Library C48972417; converted for engineering review. '
                  'https://lceda.cn/ https://easyeda.com ; manufacturer HW/stencil approval pending.')
cx, cy = package['head']['x'], package['head']['y']
def point(x, y):
    return p.VECTOR2I(p.FromMM((float(x)-cx)*.254), p.FromMM((float(y)-cy)*.254))
pads = []
for shape in package['shape']:
    fields = shape.split('~')
    if fields[0] != 'PAD':
        continue
    assert fields[1] == 'RECT' and fields[6] == '1' and float(fields[9]) == 0
    x, y, width, height = map(float, fields[2:6])
    angle = float(fields[11])
    assert angle in (0, 90, 180, 270)
    polygon = list(map(float, fields[10].split()))
    pw, ph = max(polygon[::2])-min(polygon[::2]), max(polygon[1::2])-min(polygon[1::2])
    expected = (height, width) if angle % 180 else (width, height)
    assert abs(pw-expected[0]) < .002 and abs(ph-expected[1]) < .002
    number = fields[8]
    pad = p.PAD(fp)
    pad.SetNumber(number)
    pad.SetAttribute(p.PAD_ATTRIB_SMD)
    pad.SetShape(p.PAD_SHAPE_RECT)
    layers = p.LSET(); [layers.AddLayer(l) for l in (p.F_Cu, p.F_Paste, p.F_Mask)]
    pad.SetLayerSet(layers)
    pad.SetPosition(point(x, y))
    pad.SetSize(p.VECTOR2I(p.FromMM(width*.254), p.FromMM(height*.254)))
    pad.SetOrientationDegrees(-angle)
    fp.Add(pad)
    pads.append({'number': number, 'x_mm': round((x-cx)*.254, 6),
                 'y_mm': round((y-cy)*.254, 6), 'width_mm': round(width*.254, 6),
                 'height_mm': round(height*.254, 6), 'rotation_deg': -angle})
assert len(pads) == 109 and {s['number'] for s in pads} == set(names)
for layer, x1, y1, x2, y2 in [(p.F_Fab,-7.9,-8.85,7.9,8.85),
                              (p.F_CrtYd,-8.5,-9.35,8.5,9.35)]:
    corners = [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
    for a,b in zip(corners, corners[1:]+corners[:1]):
        line = p.PCB_SHAPE(fp); line.SetShape(p.SHAPE_T_SEGMENT); line.SetLayer(layer)
        line.SetStart(p.VECTOR2I(p.FromMM(a[0]),p.FromMM(a[1])))
        line.SetEnd(p.VECTOR2I(p.FromMM(b[0]),p.FromMM(b[1])))
        line.SetWidth(p.FromMM(.05 if layer == p.F_CrtYd else .1)); fp.Add(line)
fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
p.FootprintSave(str(ROOT/'VoiceV2.pretty'), fp)
audit = {
    'model': 'ML307C-DL', 'part_number': 'C48972417', 'retrieved_date': '2026-11-22',
    'source_name': '嘉立创EDA/EasyEDA官方库 / JLCEDA/EasyEDA Official Library',
    'source_url': 'https://easyeda.com/api/products/C48972417/components?version=6.4.19.5',
    'homepages': ['https://lceda.cn/', 'https://easyeda.com'],
    'library_attribution': symbol['head'].get('license', ''),
    'symbol_uuid': source['uuid'], 'footprint_uuid': source['packageDetail']['uuid'],
    'raw_sha256': hashlib.sha256(raw).hexdigest(), 'pin_names': names, 'pads': pads,
    'verified': {'library_has_109_unique_pins_and_pads': True, 'rectangles_match_source_polygons': True,
                 'manufacturer_hardware_manual': False, 'voltage_timing_and_AT_compatibility': False,
                 'stencil_and_real_part_fit': False},
}
(ROOT/'sources').mkdir(exist_ok=True)
(ROOT/'sources/ml307c-dl-library.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Prepared C-DL-specific candidate: 109 pins/pads, source polygons checked; hardware approval pending.')
