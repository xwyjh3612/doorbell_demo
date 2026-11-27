"""Export a routing pass with ground reserved for reviewed pours/stitching.

The router input keeps every ground pin in a dedicated GROUND class. Run
Freerouting with router.autorouter.ignore_net_classes=["GROUND"]. Final
ground pours/stitching and native DRC must account for every ground pad.
"""
from pathlib import Path
import re, os, json, hashlib
import pcbnew as p
FILE = Path(os.environ['A18_REPAIR_BOARD']).resolve()
OUT = FILE.parent
b = p.LoadBoard(str(FILE))
assert b.GetCopperLayerCount() == 2
assert p.ExportSpecctraDSN(b, str(OUT / 'signals.dsn'))
text = (OUT / 'signals.dsn').read_text(encoding='utf-8')
large, small = 'Via[0-1]_600:300_um', 'Via[0-1]_450:200_um'
if small not in text:
    at = text.index('    (padstack "' + large + '"')
    end = text.index('\n    )', at) + len('\n    )')
    block = text[at:end].replace(large, small).replace(' 600', ' 450').replace(' 300', ' 200')
    text = text[:end] + '\n' + block + text[end:]
text = text.replace('(use_via "' + large + '")', '(use_via "' + small + '")')
text = re.sub(r'\(width 200\)', '(width 160)', text)
power = ['BAT_BOOST_5V', 'BAT_SENSE_IN', 'CELL_NEG', 'ESP_3V3', 'MODEM_3V8', 'SYS_5V', 'VIN_PROTECTED', 'BUCK_SW', 'UPS_SW', 'ESP_SW']
fused = ['VIN_DC', 'VIN_FUSED']
start = text.index('    (class kicad_default')
end = text.index('      (circuit', start)
head = text[start:end]
for net in power + fused + ['GND']:
    head = re.sub(r'(?<![\w])' + re.escape(net) + r'(?![\w])', '', head)
text = text[:start] + head + text[end:]
extra = '    (class POWER ' + ' '.join(power) + ' (circuit (use_via "' + large + '")) (rule (width 250) (clearance 200)))\n'
extra += '    (class FUSED_INPUT ' + ' '.join(fused) + ' (circuit (use_via "' + large + '")) (rule (width 800) (clearance 200)))\n'
plane_ground=os.environ.get('A18_ROUTER_GROUND_MODE')=='plane'
if not plane_ground:
    extra += '    (class GROUND GND (circuit (use_via "' + large + '")) (rule (width 250) (clearance 200)))\n'
text = text.replace('  )\n  (wiring', extra + '  )\n  (wiring', 1)
if plane_ground:
    # Only the external router input omits ground routing. Physical pad shapes
    # remain obstacles; saved PCB/netlist ground pins are never changed. All
    # grounds must be accounted for by pours/stitching and final native DRC.
    at=text.index('    (net GND\n')
    opening=text.index('(',at);depth=0;end=None
    for i in range(opening,len(text)):
        if text[i]=='(':depth+=1
        elif text[i]==')':
            depth-=1
            if depth==0:end=i+1;break
    assert end is not None
    text=text[:at]+text[end:]
    text='\n'.join(line for line in text.splitlines() if '(net GND)' not in line)+'\n'
    assert '(net GND)' not in text and '(net GND\n' not in text
(OUT / 'signals.dsn').write_text(text, encoding='utf-8')
(OUT/'exports/router-input-scope.json').write_text(json.dumps({'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),
    'ground_mode':'plane-only-router-input' if plane_ground else 'GROUND-class',
    'saved_PCB_ground_pins_preserved':True,'final_native_DRC_must_include_ground':True},indent=2),encoding='utf-8')
print('Two-layer routing input exported; ground remains mandatory in saved PCB and final DRC.')
