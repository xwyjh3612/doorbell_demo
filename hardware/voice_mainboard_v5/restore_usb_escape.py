"""Restore the pending USB branch escape and route from its real copper via."""
from pathlib import Path
import json
import pcbnew as p
from two_layer_support import load
ROOT=Path(__file__).resolve().parent
r,m=load();b=r.board;file=ROOT/'voice_mainboard_v5.kicad_pcb'
name='RESTORED_DP'
r.addvia(name,'ESP_USB_DP20',(77.8,30.1))
r.virtual[name].IsOnLayer=lambda li:li in [p.F_Cu,p.B_Cu]
targets=[(88.8,29.9),(88.8,28.2)]
report=[]
for i,xy in enumerate(targets):
    target='RESTORED_DP_TARGET_'+str(i)
    r.virtual[target]=r.Endpoint('ESP_USB_DP20',xy)
    r.virtual[target].IsOnLayer=lambda li:li in [p.F_Cu,p.B_Cu]
    try:
        result=m.route(r,(name,0),(target,0),width=.2,step=.05,bounds=(72,23,96,40))
        report.append({'connected':True,**result});break
    except RuntimeError as e:report.append({'connected':False,'reason':str(e)})
assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
(ROOT/'exports/usb-restored-escape.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
