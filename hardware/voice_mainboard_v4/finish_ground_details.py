"""Finish resistor ground escapes and a conventional QFN exposed-pad via.

The QFN uses four paste windows (about 60% of exposed-pad area) and one
0.3 mm thermal drill, bottom tented. This is a candidate stencil pattern;
manufacturer/assembler approval and prototype voiding inspection are pending.
"""
from pathlib import Path
import json,pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
scope={'__file__':str(ROOT/'connect_ground_lobes.py')}
exec(compile((ROOT/'connect_ground_lobes.py').read_text(encoding='utf8').split('pairs =')[0],'router','exec'),scope)
r=scope['r'];b=r.board;held=[];report=[]
for pair in [('R5',2),('R60',2)]:
    try:r.escapevia('FINAL_GND_'+pair[0],pair);report.append({'pad':pair,'connected':True})
    except RuntimeError as e:report.append({'pad':pair,'connected':False,'reason':str(e)})
fp=next(f for f in b.GetFootprints()if f.GetReference()=='U14')
for pd in list(fp.Pads()):
    if pd.GetNumber()==''and pd.IsOnLayer(p.F_Paste):fp.Remove(pd);held.append(pd)
for dx in [-.45,.45]:
    for dy in [-.45,.45]:
        pd=p.PAD(fp);pd.SetNumber('');pd.SetAttribute(p.PAD_ATTRIB_SMD);pd.SetShape(p.PAD_SHAPE_RECT)
        pd.SetSize(p.VECTOR2I(p.FromMM(.65),p.FromMM(.65)))
        pd.SetPosition(p.VECTOR2I(p.FromMM(92+dx),p.FromMM(19+dy)))
        layers=p.LSET();layers.AddLayer(p.F_Paste);pd.SetLayerSet(layers);fp.Add(pd);held.append(pd)
if not any(isinstance(t,p.PCB_VIA)and r.pos(t)==(92,19)for t in b.GetTracks()):
    r.addvia('AMP_EP_THERMAL','GND',(92,19))
    via=next(t for t in b.GetTracks()if isinstance(t,p.PCB_VIA)and r.pos(t)==(92,19))
    via.SetBackTentingMode(p.TENTING_MODE_TENTED)
report.append({'pad':['U14',17],'thermal_via_mm':[92,19],'diameter_mm':.6,'drill_mm':.3,'back_tented':True,'paste_windows':4,'paste_area_fraction':4*.65*.65/(1.675*1.675),'assembler_approved':False})
drc=json.loads((ROOT/'exports/routed-drc.json').read_text(encoding='utf8'))
tails={i['uuid']for v in drc['violations']if v['type']in ['via_dangling','track_dangling']for i in v['items']}
for t in list(b.GetTracks()):
    if t.m_Uuid.AsString()in tails and t.GetNetname()not in ['POWER_BUS','GND']:
        b.Remove(t);held.append(t)
p.SaveBoard(str(file),b)
(ROOT/'exports/ground-details.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(report)
