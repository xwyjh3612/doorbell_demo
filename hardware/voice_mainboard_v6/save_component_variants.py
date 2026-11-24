"""Freeze the verified pad geometry of the two multi-pad component variants."""
from pathlib import Path
import collections,json,pcbnew as p
ROOT=Path(__file__).resolve().parent;FILE=ROOT/'voice_mainboard_v6.kicad_pcb';LIB=ROOT.parents[1]/'build/cad-tools/kicad/share/kicad/footprints'
b=p.LoadBoard(str(FILE));d=json.loads((ROOT/'design.json').read_text(encoding='utf8'));parts={q['ref']:q for q in d['parts']};report=[]
def geometry(fp):
    return collections.Counter((pd.GetNumber(),round(p.ToMM(pd.GetPosition().x),5),round(p.ToMM(pd.GetPosition().y),5),
        round(p.ToMM(pd.GetSize().x),5),round(p.ToMM(pd.GetSize().y),5),int(pd.GetShape()),int(pd.GetAttribute())) for pd in fp.Pads() if pd.GetAttribute()==p.PAD_ATTRIB_SMD and (pd.IsOnLayer(p.F_Cu) or pd.IsOnLayer(p.B_Cu)))
for f in b.GetFootprints():
    ref=f.GetReference()
    if ref not in ['U7','U14']:continue
    old=parts[ref]['footprint'];lib,name=old.split(':');std=p.FootprintLoad(str(LIB/(lib+'.pretty')),name)
    copy=p.FOOTPRINT(f);copy.SetOrientationDegrees(0);copy.SetPosition(p.VECTOR2I(0,0))
    assert geometry(copy)==geometry(std),(ref,list((geometry(copy)-geometry(std)).elements()))
    variant='V6_'+ref+'_SMD_LAND_MATCH';id=p.LIB_ID('VoiceV2',variant);copy.SetFPID(id)
    copy.SetReference('REF**');copy.SetValue(variant);copy.SetPath(p.KIID_PATH())
    for pd in copy.Pads():pd.SetNetCode(0)
    copy.SetLibDescription('SMD land geometry matches KiCad9 '+old+'. Preserves customized stencil apertures and board thermal holes. Stencil and thermal-hole process require assembler review.')
    p.FootprintSave(str(ROOT/'VoiceV2.pretty'),copy);f.SetFPID(id);parts[ref]['footprint']='VoiceV2:'+variant
    report.append({'ref':ref,'original_library':old,'SMD_land_geometry_matches_original':True,'SMD_pads_checked':sum(geometry(copy).values()),'paste_apertures_qualified':False,
        'thermal_plated_holes':[{'pad':pd.GetNumber(),'diameter_mm':p.ToMM(pd.GetSize().x),'drill_mm':p.ToMM(pd.GetDrillSize().x)} for pd in copy.Pads() if pd.GetAttribute()==p.PAD_ATTRIB_PTH]})
(ROOT/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'exports/component-land-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');p.SaveBoard(str(FILE),b);print(report)
