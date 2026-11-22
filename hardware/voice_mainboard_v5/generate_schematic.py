"""Generate the new pin-label contract sheet without invoking the V4 generator."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = (ROOT.parent/'voice_mainboard_v2/generate_schematic.py').read_text(encoding='utf8')
source = source.replace("PROJECT='voice_mainboard_v2'", "PROJECT='voice_mainboard_v5'").replace("'voice-mainboard-v2/'", "'voice-mainboard-v5/'")
start = source.index('groups=[')
end = source.index('rootuid=UID',start)
source = source[:start] + '''groups=[
 ('01 INPUT / MODEM 3.77856V',[]),
 ('02 UPS 5V CONTRACT - IC TBD',[]),
 ('03 ML307 / UART / RESET',[]),
 ('04 SIM / RF / USB RESERVE',[]),
 ('05 ESP / BOOT / ADC / TTL',[]),
 ('06 ESP3.315V / I2S AUDIO',[]),
 ('07 TEST PADS',[])]
for ref,p in parts.items():groups[int(p['group'][:2])-1][1].append(ref)
''' + source[end:]
source = source.replace('(paper "A0")', '(paper "User" 1250 1000)')
source = source.replace('VOICE INTERCOM - ML307R-DL SMT / UPS RESERVED', 'VOICE INTERCOM - V5 REGULATED UPS 5V / ESP32 / ML307C-DL')
source = source.replace('2026-11-21','2026-11-22').replace('V2-UNROUTED','V5-UPS-CONTRACT')
source = source.replace('DC 4.5-5.5V, nominal 5V/2A; separate 3.8V and 5V rails; future UPS plug-in', 'UPS OUTPUT ASSUMED regulated5V; internal UPS circuit and footprint TBD')
source = source.replace('109-pad land pattern transcribed from manufacturer; release signoff pending', 'C-DL109pads JLCEDA/EasyEDA Official Library; manufacturer HW review pending')
source = source.replace('assert yc<785','assert yc<900')
start = source.index("text('UPS RESERVE:")
end = source.index("lib.append('''",start)
source = source[:start] + '''text('V5: assumed UPS5V -> modem TPS5632013.77856V; ESP SY8089A13.31493V; audio/radar direct5V.',25,925,1.7)
text('U15 is an electrical interface with reserved area, not a selected charging IC or verified UPS circuit.',25,935,1.7)
text('J18 TTL = GND / ESP TX43 / ESP RX44 / adapter5V. Do not parallel TTL5V and main adapter.',25,945,1.7)
text('SIM JAE footprint retained until exact cheap socket drawing; GPIO6/8 radar and official protocol unchanged.',25,955,1.7)
text('Electrical/geometry checks do not validate load, startup, temperature, RF, USB or call function.',25,965,1.7)
''' + source[end:]
source = source.replace("['VIN_DC','POWER_BUS','SYS_5V','ESP_3V3','GND','MODEM_3V8','USB_DETECT_5V']", "['VIN_DC','VIN_PROTECTED','ESP_3V3','GND','MODEM_3V8','USB_DETECT_5V']")
source = source.replace('770.89','909.32').replace('A0 review sheet','V5 review sheet')
exec(compile(source,str(Path(__file__).resolve()),'exec'),globals())
