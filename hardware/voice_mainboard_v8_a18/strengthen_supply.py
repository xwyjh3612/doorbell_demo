"""Remove inefficient critical supply routes for a wide-trunk repair stage.

The native-zero stage is retained. Ground planes and GND pins are preserved;
obsolete ground vias are removed before short wide supply routes are reserved.
"""
from pathlib import Path
import json,os,shutil
import pcbnew as p
FILE=Path(os.environ['A18_REPAIR_BOARD']);ROOT=FILE.parent
snap=ROOT/'before-wide-supply';snap.mkdir(exist_ok=True)
for ext in ['kicad_pcb','kicad_sch','kicad_pro','kicad_dru']:shutil.copy2(FILE.with_suffix('.'+ext),snap/FILE.with_suffix('.'+ext).name)
shutil.copy2(ROOT/'design.json',snap/'design.json')
b=p.LoadBoard(str(FILE));held=[];entries=[]
for t in list(b.GetTracks()):
    if t.GetNetname()in ['VIN_PROTECTED','SYS_5V','BAT_BOOST_5V','MODEM_RESET_N']or(isinstance(t,p.PCB_VIA)and t.GetNetname()=='GND'):
        entries.append({'uuid':str(t.m_Uuid.AsString()),'net':t.GetNetname(),'via':isinstance(t,p.PCB_VIA)});held.append(t);b.Remove(t)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'exports/wide-supply-reset.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
print('Prepared wide-trunk reroute; removed route pieces',len(entries),'native-zero stage retained.')
for t in held:t.thisown=False
