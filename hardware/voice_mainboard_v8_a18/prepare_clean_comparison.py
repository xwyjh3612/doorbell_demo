"""Isolated routing assessment without historical detours or surface pours.

The work PCB is never overwritten. Native KiCad checking remains mandatory.
"""
from pathlib import Path
import json, re, shutil, sys
import pcbnew as p

ROOT=Path(__file__).resolve().parent
count=int(sys.argv[1]) if len(sys.argv)>1 else 4
assert count in [2,4]
OUT=ROOT/f'comparison_clean_{count}layer'
OUT.mkdir(exist_ok=True)
NAME=f'voice_mainboard_a18_clean_{count}layer'
for ext in ['kicad_sch','kicad_pro','kicad_dru']:
    shutil.copy2(ROOT/('voice_mainboard_v8_a18.'+ext),OUT/(NAME+'.'+ext))
for table in ['fp-lib-table','sym-lib-table']:
    (OUT/table).write_text((ROOT/table).read_text(encoding='utf-8').replace('${KIPRJMOD}/','${KIPRJMOD}/../'),encoding='utf-8')
board=p.LoadBoard(str(ROOT/'voice_mainboard_v8_a18.kicad_pcb'))
held=[]
for item in list(board.GetTracks()):
    held.append(item);board.Remove(item)
for zone in list(board.Zones()):
    if not zone.GetIsRuleArea():held.append(zone);board.Remove(zone)
board.SetCopperLayerCount(count)
board.BuildConnectivity()
file=OUT/(NAME+'.kicad_pcb')
p.SaveBoard(str(file),board)
assert p.ExportSpecctraDSN(board,str(OUT/'clean.dsn'))
text=(OUT/'clean.dsn').read_text(encoding='utf-8')
# No early surface planes: the router must reserve signal corridors first.
large=f'Via[0-{count-1}]_600:300_um'
small=f'Via[0-{count-1}]_450:200_um'
if small not in text:
    at=text.index('    (padstack "'+large+'"')
    end=text.index('\n    )',at)+len('\n    )')
    block=text[at:end].replace(large,small).replace(' 600',' 450').replace(' 300',' 200')
    text=text[:end]+'\n'+block+text[end:]
text=text.replace('(use_via "'+large+'")','(use_via "'+small+'")')
power=['BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','ESP_3V3','MODEM_3V8','SYS_5V','VIN_PROTECTED']
fused=['VIN_DC','VIN_FUSED']
start=text.index('    (class kicad_default');end=text.index('      (circuit',start)
head=text[start:end]
for net in power+fused:head=re.sub(r'(?<![\w])'+re.escape(net)+r'(?![\w])','',head)
text=text[:start]+head+text[end:]
extra='    (class POWER '+' '.join(power)+' (circuit (use_via "'+large+'")) (rule (width 400) (clearance 200)))\n'
extra+='    (class FUSED_INPUT '+' '.join(fused)+' (circuit (use_via "'+large+'")) (rule (width 800) (clearance 200)))\n'
text=text.replace('  )\n  (wiring',extra+'  )\n  (wiring',1)
(OUT/'clean.dsn').write_text(text,encoding='utf-8')
design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
design.update(layers=count,revision=f'A18 CLEAN {count}-LAYER ROUTING ASSESSMENT',manufacturing_ready=False)
(OUT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Prepared independent {count}-layer assessment; all original routing evidence retained',flush=True)
for item in held:item.thisown=False
