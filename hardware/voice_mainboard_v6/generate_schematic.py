"""Generate native pin/net schematic from the V6 circuit contract."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
source=(ROOT.parent/'voice_mainboard_v5/generate_schematic.py').read_text(encoding='utf8')
source=source.replace("ROOT.parent/'voice_mainboard_v2/generate_schematic.py'","ROOT.parent/'voice_mainboard_v2/generate_schematic.py'")
source=source.replace('voice_mainboard_v5','voice_mainboard_v6').replace('voice-mainboard-v5/','voice-mainboard-v6/')
source=source.replace('02 UPS 5V CONTRACT - IC TBD','02 ETA1096 / CHARGE / PROTECT / MUX')
source=source.replace('01 INPUT / MODEM 3.77856V','01 INPUT / MODEM 3.80856V')
source=source.replace('V5 review sheet','V6 review sheet').replace('V5:','V6:')
source=source.replace('V5 REGULATED UPS 5V','V6 INTEGRATED UPS').replace('V5-UPS-CONTRACT','V6-INTEGRATED-UPS')
source=source.replace('UPS OUTPUT ASSUMED regulated5V; internal UPS circuit and footprint TBD','ETA1096 battery boost + hardware priority mux; external5V direct path')
source=source.replace('2026-11-22','2026-11-24').replace("assert yc<900","assert yc<1200")
source=source.replace('(paper "User" 1250 1000)','(paper "User" 1250 1350)')
source=source.replace('assumed UPS5V -> modem TPS5632013.77856V; ESP SY8089A13.31493V; audio/radar direct5V.','V6 UPS: ETA1096 battery boost + TPS2117 external priority; two SY8089A1 bucks; nominal5V audio/radar.')
source=source.replace('U15 is an electrical interface with reserved area, not a selected charging IC or verified UPS circuit.','Battery J23 = CELL+ / isolated CELL- / NTC. CELL- must NOT short to systemGND; U17 is protection.')
source=source.replace('GPIO6/8 radar and official protocol unchanged.','GPIO6/8 radar; GPIO47 muxST; ADC2 with GPIO9 gate; GPIO38 charge pause; GPIO48/1 charge status.')
for old,new in [('25,925','25,1250'),('25,935','25,1260'),('25,945','25,1270'),('25,955','25,1280'),('25,965','25,1290'),('909.32','1235.71')]:source=source.replace(old,new)
# Match the actual PCB net names and values so native schematic parity works.
insertion = 'source = source.replace(' + repr('(label {Q(name)} (at') + ', ' + repr('(global_label {Q(name)} (shape input) (at') + ')\n'
insertion += 'source = source.replace(' + repr('(label "{name}" (at') + ', ' + repr('(global_label "{name}" (shape input) (at') + ')\n'
insertion += 'source = source.replace(' + repr('p["value"]+(" [DNP]" if p["dnp"] else "")') + ', ' + repr('p["value"]') + ')\n'
insertion += 'source = source.replace(' + repr("        dnp='yes' if p['dnp'] else 'no'") + ', ' + repr("        inbom='no' if ref.startswith('TP') else 'yes'\n        dnp='yes' if p['dnp'] else 'no'") + ')\n'
insertion += 'source = source.replace(' + repr('(unit 1) (in_bom yes) (on_board yes) (dnp {dnp})') + ', ' + repr('(unit 1) (in_bom {inbom}) (on_board yes) (dnp {dnp})') + ')\n'
source=source.replace('exec(compile(source',insertion+'exec(compile(source')
# Execute the existing generator with this V6 root, never the V5 root.
exec(compile(source,str(Path(__file__).resolve()),'exec'),globals())
