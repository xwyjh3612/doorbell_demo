"""Create a separate same-mechanics four-layer routing assessment."""
from pathlib import Path
import json,re,shutil
import pcbnew as p
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'comparison_4layer';OUT.mkdir(exist_ok=True)
NAME='voice_mainboard_a18_4layer_comparison'
for ext in ['kicad_sch','kicad_pro','kicad_dru']:
    shutil.copy2(ROOT/('voice_mainboard_v8_a18.'+ext),OUT/(NAME+'.'+ext))
for table in ['fp-lib-table','sym-lib-table']:
    text=(ROOT/table).read_text(encoding='utf-8').replace('${KIPRJMOD}/','${KIPRJMOD}/../')
    (OUT/table).write_text(text,encoding='utf-8')
b=p.LoadBoard(str(ROOT/'voice_mainboard_v8_a18.kicad_pcb'));b.SetCopperLayerCount(4)
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):t.SetLocked(False)
    else:t.SetLocked(p.ToMM(t.GetWidth())>=.4 or p.ToMM(t.GetWidth())<.18)
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'));pts=data['mechanical']['outline_mm']
z=p.ZONE(b);z.SetLayer(p.In1_Cu);z.SetNet(b.FindNet('GND'));z.SetLocalClearance(p.FromMM(.2));z.SetMinThickness(p.FromMM(.2))
z.SetPadConnection(p.ZONE_CONNECTION_FULL);z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS);z.Outline().NewOutline()
for x,y in pts:z.Outline().Append(p.FromMM(x),p.FromMM(y))
b.Add(z);b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones())
file=OUT/(NAME+'.kicad_pcb');p.SaveBoard(str(file),b)
assert p.ExportSpecctraDSN(b,str(OUT/'comparison.dsn'))
text=(OUT/'comparison.dsn').read_text(encoding='utf-8')
large='Via[0-3]_600:300_um';small='Via[0-3]_450:200_um'
assert large in text and small in text
text=text.replace('(use_via "'+large+'")','(use_via "'+small+'")')
power=['BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','ESP_3V3','MODEM_3V8','SYS_5V','VIN_PROTECTED'];fused=['VIN_DC','VIN_FUSED']
start=text.index('    (class kicad_default');end=text.index('      (circuit',start);head=text[start:end]
for net in power+fused:head=re.sub(r'(?<![\w])'+re.escape(net)+r'(?![\w])','',head)
text=text[:start]+head+text[end:]
extra='    (class POWER '+' '.join(power)+' (circuit (use_via "'+large+'")) (rule (width 250) (clearance 200)))\n'
extra+='    (class FUSED_INPUT '+' '.join(fused)+' (circuit (use_via "'+large+'")) (rule (width 800) (clearance 200)))\n'
text=text.replace('  )\n  (wiring',extra+'  )\n  (wiring',1);(OUT/'comparison.dsn').write_text(text,encoding='utf-8')
data.update(revision='A18 FOUR-LAYER COMPARISON; NOT SELECTED FOR MANUFACTURE',layers=4,manufacturing_ready=False)
(OUT/'design.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared independent four-layer comparison; original two-layer work file retained',flush=True)
