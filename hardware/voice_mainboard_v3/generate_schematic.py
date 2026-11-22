"""Reuse the audited V2 pin-map generator with V3's actual electrical nets.

The larger review sheet avoids cropping an integrated UPS into the former
reserved space. All circuits remain editable native KiCad symbols and nets.
"""
from pathlib import Path
source=(Path(__file__).resolve().parent.parent/'voice_mainboard_v2/generate_schematic.py').read_text(encoding='utf8')
source=source.replace("PROJECT='voice_mainboard_v2'","PROJECT='voice_mainboard_v3'")
source=source.replace("'voice-mainboard-v2/'","'voice-mainboard-v3/'")
source=source.replace("('07 SEPARATE SYSTEM 5V CONVERTER',[])]", "('07 SEPARATE SYSTEM 5V CONVERTER',[]),\n ('08 BATTERY PACK / CHARGER / NTC',[]),\n ('09 BACKUP BOOST / AUTOMATIC POWER MUX',[]),\n ('10 HARDWARE UV HYSTERESIS / SOURCE THRESHOLD',[])]")
source=source.replace("'06':6}[g]","'06':6,'07':7,'08':8,'09':9}[g]")
source=source.replace('(paper "A0")','(paper "User" 1680 900)')
source=source.replace('VOICE INTERCOM - ML307R-DL SMT / UPS RESERVED','VOICE INTERCOM - ML307R-DL SMT / INTEGRATED UPS')
source=source.replace('2026-11-21','2026-11-22').replace('V2-UNROUTED','V3-INTEGRATED-UPS-REVIEW')
source=source.replace('future UPS plug-in','integrated charger / boost / automatic power mux')
source=source.replace('UPS RESERVE: actual charging, cell protection, power path, NTC and current limits must be designed after chip selection.',
 'UPS: U8 TP4056 100mA / U9 TPS61230A 4.992V / U10 TPS2117. Protected >=5A 1S pack at J2, 10k/B3950 NTC at J4.')
source=source.replace('INPUT: nominal 5V/2A, 4.5-5.5V range. F1/Q6 protection; JP4 selects direct or future UPS; parallel 3.8V/5V rails.',
 'INPUT: nominal 5V/2A, 4.5-5.5V range. JP4 2-3 = onboard UPS NORMAL; 1-2 = adapter diagnostic bypass. Only one shunt.')
source=source.replace('J13 pins28/29 NC. Hardware USB test pending.','J13 pin28 charge-disable GPIO38, pin29NC. Hardware USB test pending.')
source=source.replace("'GND','MODEM_3V8','USB_DETECT_5V']", "'GND','MODEM_3V8','USB_DETECT_5V','BAT_SENSE_IN','UPS_CTL_VCC','VIN_PROTECTED']")
source=source.replace('A0 review sheet','integrated UPS review sheet')
exec(compile(source,str(Path(__file__).resolve()),'exec'),globals())
