"""Keep the reviewed manufacturer jack geometry in the project library."""
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
fp=next(f for f in b.GetFootprints() if f.GetReference()=='J1')
assert fp.GetFPID().GetLibItemName()=='HX_DC005_2p5_T'
assert {pd.GetNumber():pd.GetNetname() for pd in fp.Pads()}=={'4':'VIN_DC','3':'','2':'GND'}
copy=fp.Duplicate()
copy.SetPosition(p.VECTOR2I(0,0));copy.SetOrientationDegrees(0)
copy.SetReference('REF**');copy.SetValue('HX_DC005_2p5_T')
for pd in copy.Pads():pd.SetNetCode(0)
plugin=p.PCB_IO_MGR.PluginFind(p.PCB_IO_MGR.KICAD_SEXP)
plugin.FootprintSave(str(root/'VoiceV2.pretty'),copy)
print('Saved exact checked jack geometry to local library')
