"""Warm routing with local necks; preserves source PCB and requires power review.

The export allows narrow power-pad escapes, not a 2A track-width approval.
Original netclass and fused-input DRC rules remain in the KiCad project.
"""
from pathlib import Path
import json, re, shutil
import pcbnew as p

ROOT = Path(__file__).resolve().parent
FILE = ROOT/'voice_mainboard_v8_a18.kicad_pcb'
snap = ROOT/'history/first-route'
snap.mkdir(exist_ok=True)
shutil.copy2(FILE, snap/FILE.name)
b = p.LoadBoard(str(FILE))
for zone in b.Zones():
    if not zone.GetIsRuleArea() and zone.GetNetname() == 'GND':
        zone.SetPadConnection(p.ZONE_CONNECTION_THT_THERMAL)
        zone.SetThermalReliefSpokeWidth(p.FromMM(.25))
b.BuildConnectivity()
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(FILE), b)
export = ROOT/'exports/completion.dsn'
assert p.ExportSpecctraDSN(b, str(export))
text = export.read_text(encoding='utf-8')
pattern = r'(\(class POWER\s+.*?\(rule\s+\(width )800(\))'
text, count = re.subn(pattern, lambda m:m[1]+'250'+m[2], text, flags=re.S)
assert count == 1
# Fuse neck width is an explicit independent DRC rule; retain it in routing.
text = text.replace('      VIN_DC VIN_FUSED VIN_PROTECTED', '      VIN_PROTECTED')
mark = '    (class RF RF_ANT RF_FEED'
assert mark in text
text = text.replace(mark, '''    (class FUSED_INPUT VIN_DC VIN_FUSED
      (circuit (use_via "Via[0-1]_600:300_um"))
      (rule (width 800) (clearance 200))
    )
'''+mark)
export.write_text(text, encoding='utf-8')
print('Exported completion DSN; power necks require independent width/voltage-drop review')
