"""Escape dense module/QFN pins before long signals can enclose pad exits.

0.45/0.20mm ordinary through vias with off-pad drills; 0.16mm short necks.
JLCPCB's published preferred minimum drill is0.2mm. Native0.2mm copper
clearance and0.1mm annular ring requirements remain unchanged.
"""
from pathlib import Path
import json,shutil,sys
import pcbnew as p
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v8_a18.kicad_pcb'
snap=ROOT/'history/before-dense-pin-fanout';snap.mkdir(exist_ok=True)
for f in [FILE,ROOT/'voice_mainboard_v8_a18.kicad_pro']:shutil.copy2(f,snap/f.name)
board=p.LoadBoard(str(FILE));held=[]
nets=['MODEM_PWRKEY_N','MODEM_RESET_N','MODEM_NETLIGHT','MODEM_STATE_1V8','MODEM_1V8',
      'SIM_VCC','M_RX_1V8','M_TX_1V8','M_DTR_1V8','M_SIM_RESET','M_SIM_CLK','M_SIM_DATA',
      'DBG_RX_1V8','DBG_TX_1V8','MODEM_BOOT_N','SIM_DETECT','M_USB_DP','M_USB_DM','USB_DETECT_5V',
      'I2S_SPK_DATA7','I2S_SPK_WS16','I2S_SPK_BCLK15','AMP_GAIN','AMP_SD','SPK_PLUS','SPK_MINUS']
for t in list(board.GetTracks()):
    if t.GetNetname()in nets:held.append(t);board.Remove(t)
board.BuildConnectivity();assert p.ZONE_FILLER(board).Fill(board.Zones());p.SaveBoard(str(FILE),board)
pro=ROOT/'voice_mainboard_v8_a18.kicad_pro';config=json.loads(pro.read_text(encoding='utf-8'))
config['board']['design_settings']['rules']['min_through_hole_diameter']=.2
config['board']['design_settings']['rules']['min_via_diameter']=.45
pro.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
wrapper=(ROOT.parent/'voice_mainboard_v4/connect_ground_lobes.py').read_text(encoding='utf-8').split('pairs =')[0]
wrapper=wrapper.replace("file = ROOT / 'voice_mainboard_v4.kicad_pcb'", "file = ROOT / 'voice_mainboard_v8_a18.kicad_pcb'")
scope={'__file__':str(ROOT/'fanout_dense_signals.py')};exec(compile(wrapper,'dense_pin_escape','exec'),scope);r=scope['r']
pairs=[('U1',n)for n in [16,17,18,19,15,11,12,13,14,7,24,25,38,39,59,60,61,79,82]]
pairs += [('U14',n)for n in [1,2,4,9,10,14,16]]
report=[]
for pair in pairs:
    entry={'pad':pair};name=f'dense_{pair[0]}_{pair[1]}'
    try:
        r.escapevia(name,pair,diameter=.45,drill=.2,neck=.16)
        entry.update(success=True,via_mm=r.pos(r.virtual[name]))
    except RuntimeError as e:entry.update(success=False,reason=str(e))
    report.append(entry);p.SaveBoard(str(FILE),r.board);print(entry,flush=True)
r.board.BuildConnectivity();assert p.ZONE_FILLER(r.board).Fill(r.board.Zones());p.SaveBoard(str(FILE),r.board)
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
data['routing_process']={'signal_via_diameter_mm':.45,'signal_drill_mm':.2,'short_dense_pin_neck_mm':.16,
 'copper_clearance_mm':.2,'annular_ring_min_mm':.1,'power_vias_nominal_mm':[.6,.3],
 'capability_source':'https://jlcpcb.com/capabilities/pcb-capabilities',
 'capability_snapshot':'build/a18-pcb-capabilities.html','domestic_JLC_quote_obtained':False,
 'note':'Conventional through-hole process; no microvia or via-in-pad assumed. Current domestic order pricing still requires review.'}
(ROOT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'exports/dense-pin-fanout.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for t in held:t.thisown=False
