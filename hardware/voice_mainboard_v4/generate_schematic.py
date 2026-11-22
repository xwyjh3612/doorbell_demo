"""Editable net-labelled schematic generated from V4's actual pin contract."""
from pathlib import Path

root=Path(__file__).resolve().parent
source=(root.parent/'voice_mainboard_v2/generate_schematic.py').read_text(encoding='utf8')
source=source.replace("PROJECT='voice_mainboard_v2'","PROJECT='voice_mainboard_v4'").replace("'voice-mainboard-v2/'","'voice-mainboard-v4/'")
start=source.index('groups=[');end=source.index('rootuid=UID',start)
source=source[:start]+'''groups=[
 ('01 ADAPTER / PRIMARY 3.792V',[]),
 ('02 CHARGE / UV / MUX',[]),
 ('03 ML307 / LEVEL / CONTROL',[]),
 ('04 SIM / RF / USB RESERVE',[]),
 ('05 ESP32 / BOOT / ADC / TTL',[]),
 ('06 3.3V / 5V / I2S AUDIO',[]),
 ('07 TEST PADS',[])]
for ref,p in parts.items():groups[int(p['group'][:2])-1][1].append(ref)
'''+source[end:]
source=source.replace('(paper "A0")','(paper "User" 1250 1100)').replace('VOICE INTERCOM - ML307R-DL SMT / UPS RESERVED','VOICE INTERCOM - V4 TWO LAYER ESP32 / ML307C-DL / UPS')
source=source.replace('2026-11-21','2026-11-22').replace('V2-UNROUTED','V4-ENGINEERING-CANDIDATE')
source=source.replace('DC 4.5-5.5V, nominal 5V/2A; separate 3.8V and 5V rails; future UPS plug-in','DC 4.5-5.5V nominal5V/2A; protected battery mux before modem/ESP/audio rails')
source=source.replace('109-pad land pattern transcribed from manufacturer; release signoff pending','C-DL109pad JLCEDA/EasyEDA Official Library; manufacturer HW approval pending')
source=source.replace('assert yc<785','assert yc<1000')
start=source.index("text('UPS RESERVE:");end=source.index("lib.append('''",start)
source=source[:start]+'''text('V4: same ESP UART17/18/DTR4; MIC14/13/12; AMP15/16/7; optional radar RX6/TX8; BOOT0.',25,1020,1.7)
text('TTL J18: GND / ESP TX43 / ESP RX44 / 5V. Main input normally powers board; do not parallel independent sources.',25,1030,1.7)
text('POWER: primary3.792V + protected1S battery -> mux -> ML307; independent ESP3.3V and audio5V converters.',25,1040,1.7)
text('ENGINEERING CANDIDATE: circuit connection/DRC checks are not load, startup, thermal or call-function verification.',25,1050,1.7)
'''+source[end:]
source=source.replace("['VIN_DC','POWER_BUS','SYS_5V','ESP_3V3','GND','MODEM_3V8','USB_DETECT_5V']","['VIN_DC','VIN_PROTECTED','BAT_SENSE_IN','BAT_ALLOWED','ADAPTER_3V8','ESP_3V3','GND','UPS_CTL_VCC','USB_DETECT_5V']")
source=source.replace('770.89','1008.38').replace('A0 review sheet','V4 engineering review sheet')
exec(compile(source,str(Path(__file__).resolve()),'exec'),globals())
