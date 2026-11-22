"""Import on the exact source board and retain a recoverable before snapshot."""
from pathlib import Path
import sys,shutil,json
import pcbnew as p
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v4.kicad_pcb'
session=Path(sys.argv[1]).resolve()
assert session.is_file()
shutil.copy2(file,Path('build/voice-v4-before-ses.kicad_pcb'))
b=p.LoadBoard(str(file));assert b.GetCopperLayerCount()==2
assert p.ImportSpecctraSES(b,str(session))
p.SaveBoard(str(file),b)
(ROOT/'exports/session-import.json').write_text(json.dumps({'session':session.name,'tracks_and_vias':len(list(b.GetTracks())),
    'requires_native_DRC_and_power_RF_USB_review':True,'manufacturing_ready':False},indent=2)+'\n',encoding='utf8')
print('Imported',len(list(b.GetTracks())),'copper items')
