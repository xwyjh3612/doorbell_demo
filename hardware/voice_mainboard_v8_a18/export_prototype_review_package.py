"""Export one exact, checked PCB as a fabrication/assembly REVIEW package.

Native CAD exports are authoritative. Do not convert incomplete qualification
into a production release merely because electrical connectivity is closed.
"""
import collections
import csv
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pcbnew as p

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
BOARD = ROOT / 'power_relayout_candidate/voice_mainboard_a18_2layer.kicad_pcb'
EXPORTS = BOARD.parent / 'exports'
OUT = ROOT / 'prototype_review_20261127'
CLI = REPO / 'build/cad-tools/kicad/bin/kicad-cli.exe'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def run(*args):
    result = subprocess.run([str(CLI), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)

board_hash = sha(BOARD)
summary = read(EXPORTS / 'review-summary.json')
assert summary['PCB_sha256'] == board_hash, 'Refresh the exact PCB review before packaging'
assert summary['native_DRC_counts'] == {'violations': 0, 'schematic_parity': 0, 'unconnected_items': 0}
assert summary['ERC_violations'] == 0
assert summary['copper_layers'] == 2
assert summary['manufacturing_ready'] is False
assert not OUT.exists(), 'Keep each reviewed package immutable; do not overwrite an earlier package'

design = read(BOARD.parent / 'design.json')
board = p.LoadBoard(str(BOARD))
parts = {q['ref']: q for q in design['parts']}
fps = {f.GetReference(): f for f in board.GetFootprints()}
assert parts.keys() == fps.keys()
assert board.GetCopperLayerCount() == 2
assert abs(p.ToMM(board.GetDesignSettings().GetBoardThickness()) - 1.2) < 1e-6
for ref, part in parts.items():
    assert bool(part.get('dnp')) == fps[ref].IsDNP(), f'DNP mismatch: {ref}'
    assert part['value'] == fps[ref].GetValue(), f'Value mismatch: {ref}'

for folder in ('fabrication', 'assembly', 'source', 'verification', 'preview'):
    (OUT / folder).mkdir(parents=True, exist_ok=True)
run('pcb', 'export', 'gerbers', '--output', OUT/'fabrication', '--layers',
    'F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,Edge.Cuts',
    '--subtract-soldermask', BOARD)
run('pcb', 'export', 'drill', '--output', OUT/'fabrication', '--format', 'excellon',
    '--drill-origin', 'absolute', '--excellon-units', 'mm', '--excellon-oval-format', 'route',
    '--excellon-separate-th', '--generate-map', '--map-format', 'svg', BOARD)
run('pcb', 'export', 'pos', '--output', OUT/'assembly/placement-all-populated.csv',
    '--format', 'csv', '--units', 'mm', '--side', 'both', '--exclude-dnp', BOARD)
run('pcb', 'export', 'pos', '--output', OUT/'assembly/placement-smd.csv',
    '--format', 'csv', '--units', 'mm', '--side', 'both', '--exclude-dnp', '--smd-only',
    '--exclude-fp-th', BOARD)
run('sch', 'export', 'pdf', '--output', OUT/'source/voice-mainboard-schematic.pdf',
    '--no-background-color', '--exclude-pdf-property-popups', BOARD.with_suffix('.kicad_sch'))

# Human/BOM data is derived from actual pad/part identities and explicit source
# metadata. Missing procurement information stays missing, never an invented SKU.
records = []
for ref, f in sorted(fps.items()):
    part = parts[ref]
    x, y = p.ToMM(f.GetPosition().x), p.ToMM(f.GetPosition().y)
    has_smd = any(d.GetAttribute() == p.PAD_ATTRIB_SMD for d in f.Pads())
    has_th = any(d.GetDrillSize().x for d in f.Pads())
    is_virtual = ref.startswith('TP') or part.get('kind') == 'mechanical'
    records.append({
        'ref': ref, 'value': f.GetValue(), 'mpn': part.get('mpn', ''),
        'footprint': part['footprint'], 'lcsc': part.get('lcsc', ''),
        'quantity': 1, 'populate': not f.IsDNP(),
        'side': 'Top' if f.GetLayer() == p.F_Cu else 'Bottom',
        'x_mm': x, 'y_mm': y, 'rotation_deg': f.GetOrientationDegrees(),
        'process': 'mechanical/test' if is_virtual else 'PTH/mixed' if has_th else 'SMT' if has_smd else 'mechanical/test',
        'source': part.get('source', ''), 'note': part.get('note', ''),
        'has_catalog_number': bool(part.get('lcsc')),
    })
(OUT/'assembly/component-records.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
for filename, processes in (
    ('placement-all-populated.csv', {'SMT', 'PTH/mixed'}),
    ('placement-smd.csv', {'SMT'}),
):
    filename = OUT/'assembly'/filename
    with filename.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
        assert headers and headers[0] in ('Ref', '#Ref'), headers
        ref_field = headers[0]
        rows = list(reader)
    expected = {q['ref'] for q in records if q['populate'] and q['process'] in processes}
    rows = [q for q in rows if q[ref_field] in expected]
    assert {q[ref_field] for q in rows} == expected, f'Native placement export omitted actual parts: {filename}'
    with filename.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
grouped = collections.defaultdict(list)
for q in records:
    if q['populate'] and q['process'] != 'mechanical/test':
        grouped[(q['value'], q['footprint'], q['lcsc'], q['mpn'])].append(q['ref'])
with (OUT/'assembly/bom-populated.csv').open('w', newline='', encoding='utf-8-sig') as stream:
    writer = csv.writer(stream)
    writer.writerow(['Comment', 'Designator', 'Footprint', 'Quantity', 'LCSC Part #', 'Manufacturer Part'])
    for (value, footprint, lcsc, mpn), refs in sorted(grouped.items()):
        writer.writerow([value, ','.join(refs), footprint, len(refs), lcsc, mpn])

for suffix in ('.kicad_pcb', '.kicad_sch', '.kicad_pro', '.kicad_dru'):
    shutil.copy2(BOARD.with_suffix(suffix), OUT/'source'/BOARD.with_suffix(suffix).name)
shutil.copytree(ROOT/'VoiceV2.pretty', OUT/'source/VoiceV2.pretty')
(OUT/'source/fp-lib-table').write_text(
    '(fp_lib_table (version 7) (lib (name "VoiceV2") (type "KiCad") '
    '(uri "${KIPRJMOD}/VoiceV2.pretty") (options "") (descr "语音对讲主板封装")))\n', encoding='utf-8')
for name in ('review-summary.json', 'review-drc.json', 'erc.json', 'netlist.xml',
             'copper-path-audit.json', 'power-width-audit.json', 'model-inventory.json',
             'l5-part-selection.json', 'signal-via-manufacturing-policy.json',
             'accepted-local-layout.json', 'accepted-fixed-audio.json'):
    shutil.copy2(EXPORTS/name, OUT/'verification'/name)
for folder in ('simulation', 'electrical-audit', 'vbat-storage'):
    if (EXPORTS/folder).exists():
        shutil.copytree(EXPORTS/folder, OUT/'verification'/folder)
for name in ('review-front.png', 'review-back.png', 'mechanical-1to1.svg',
             'voice-mainboard-board-only.step', 'voice-mainboard-models.step'):
    source = EXPORTS/name
    if source.exists():
        shutil.copy2(source, OUT/'preview'/name)

dnp = [q['ref'] for q in records if not q['populate']]
missing_skus = [q['ref'] for q in records if q['populate'] and q['process'] != 'mechanical/test' and not q['lcsc']]
status = {
    'product': '语音对讲主板', 'created_at': datetime.datetime.now().astimezone().isoformat(),
    'PCB_sha256': board_hash, 'copper_layers': 2, 'outline_mm': [73, 73],
    'thickness_mm': 1.2, 'footprints': len(records),
    'native_checks': summary['native_DRC_counts'], 'ERC_violations': 0,
    'layout_connectivity_complete': True, 'manufacturing_ready': False,
    'release_type': 'fabrication-and-assembly-review-only', 'dnp': dnp,
    'parts_without_catalog_number': missing_skus,
    'remaining_validation': [
        'USB differential impedance/reference and branch topology have not been qualified',
        '2A power transients/converter stability/temperature require a physical prototype',
        'Case window/button/connector access require physical dimensions and fit verification',
        'Battery chemistry/NTC/pulse rating must match the selected protection and charger',
        'Some procurement SKUs and manufacturer land patterns require supplier confirmation',
        '80%-stop/70%-resume charging firmware is not implemented',
    ],
}
(OUT/'release-status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
notes = f'''# 语音对讲主板打样资料审查版

本包对应PCB SHA256：`{board_hash}`。两层铜，73×73mm外包尺寸，板厚1.2mm，双面贴装，保留电池仓避让。ERC、DRC、未连接及原理图一致性均为0。**本包尚未生产放行，不作为直接下单或整机性能已合格的声明。**

`fabrication`是同版Gerber和Excellon钻孔/槽孔文件，`assembly`是物料和原生KiCad坐标，`source`是原理图PDF与可编辑工程，`verification`是检查和局部模型，`preview`是板图及可用STEP。

## 贴装约定

- 默认不贴：{', '.join(dnp)}。USB维修/PC模式贴R26/R27，ESP主机模式使用R28/R29；两组不得同时贴装。先审核实际USB支路与信号完整性。
- 坐标为毫米、PCB绝对原点、KiCad原生输出坐标和角度，Bottom的X未额外镜像。坐标文件按KiCad导出规则处理Y轴方向，不可拿屏幕向下为正的坐标直接替换。测试焊盘和安装孔已从贴装坐标中排除。加工方按自身软件核对旋转、引脚1和极性，不可直接套另一厂商的角度规则。
- SMT清单排除通孔及不贴件。圆口、针座等插件见完整物料/坐标，插座槽孔保留为铣槽钻孔。
- 未填写采购编号的已贴装元件：{', '.join(missing_skus)}。空编号不能当作嘉立创已经有料；有编号的元件也需核型号、参数、封装和当前库存。
- 普通过孔最小孔径0.20mm、外径0.40mm，环宽0.10mm；密集封装使用普通引出，不按填孔盘中孔处理。公开工艺资料提示这种孔径/外径组合可能加价，下单方需确认国内实际工艺和报价。

## 电源和接口

- 外电采用5V/2A作为开发验证基线，正极圆口中心，电源路径经过保险丝、反接保护和切换芯片。外电时SYS_5V为切换后的输入电压，并非额外稳压到精确5.000V。
- 电池为单节4.2V体系，电池接口BAT+、CELL_NEG、NTC。CELL_NEG不能并接系统GND，否则绕过电池保护。温度线按10k/B3950假设，实际电芯与NTC未冻结。
- 当前充电设定100mA，GPIO38可暂停充电。80%停充/70%恢复尚需固件实现和电芯校准，不能当作已有功能。
- 不装电池时外电路径独立存在，样板应先验证无电池冷启动，再测试充电和断电切换。
- 四针TTL：GND、ESP TX43、ESP RX44、5V供电。TX/RX为3.3V逻辑，不得用5V逻辑；已有外电时不要把另一5V电源直接并上。
- 喇叭接SPK+与SPK-，两端都不是GND。功放固定12dB、左声道，铜连接替代原两颗固定0Ω跳线。
- 圆口插座开口名义位置在PCB右边外6mm，需要壳体开窗及实物插头确认；不据无完整元件模型的STEP断言装壳无碰撞。

## 尚需完成的工程验证

USB差分阻抗/参考地/支路、电源峰值与温升、供应商封装和实物装壳仍未闭环。局部SPICE模型未模拟ESP32、4G内部、化学电池或整板热行为。现有开发板长通话结果不代表新板已测试。

样板验证顺序：限流检查短路；无电池外电启动；测3.8V/3.3V及开关节点；4G入网和双向通话时在模组电源脚记录示波器波形；断电切换；低电量与NTC温度暂停充电；检查电池保护；长通话和温升。真实上电记录产生前，不能保证2A动态供电已合格。
'''
(OUT/'README.md').write_text(notes, encoding='utf-8')
assert sha(BOARD) == board_hash, 'Board changed while exporting'
manifest = {str(f.relative_to(OUT)).replace('\\', '/'): sha(f) for f in sorted(OUT.rglob('*')) if f.is_file()}
(OUT/'manifest.json').write_text(json.dumps({'PCB_sha256': board_hash, 'files': manifest}, indent=2), encoding='utf-8')
zip_path = OUT.with_suffix('.zip')
assert not zip_path.exists()
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
    for f in sorted(OUT.rglob('*')):
        if f.is_file():
            archive.write(f, str(f.relative_to(OUT.parent)))
with zipfile.ZipFile(zip_path) as archive:
    assert archive.testzip() is None
print(json.dumps({'folder': str(OUT), 'zip': str(zip_path), **status}, ensure_ascii=False, indent=2))
