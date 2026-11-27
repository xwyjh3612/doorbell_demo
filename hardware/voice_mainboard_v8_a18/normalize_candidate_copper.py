"""Correct imported via drills and preserve the fused-input width requirement.

KiCad's SES import may use a netclass drill preference with a smaller imported
via diameter. Correct actual holes, never lower the annular-ring design rule.
"""
import datetime,json,shutil
import pcbnew as p
from comparison_route_geometry import b,FILE

snapshot=FILE.parent/'iterations'/('before-import-geometry-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True);shutil.copy2(FILE,snapshot/FILE.name)
changes=[]
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):
        diameter=p.ToMM(t.GetWidth(p.F_Cu));drill=p.ToMM(t.GetDrill())
        if diameter-drill<.2-1e-6:
            assert diameter>=.45 and drill>=.2
            t.SetDrill(p.FromMM(.2))
            changes.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'via_diameter_mm':diameter,'old_drill_mm':drill,'new_drill_mm':.2})
    elif t.GetNetname()=='VIN_FUSED'and p.ToMM(t.GetWidth())<.5:
        changes.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'old_width_mm':p.ToMM(t.GetWidth()),'new_width_mm':.5})
        t.SetWidth(p.FromMM(.5))
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(FILE.parent/'exports/imported-copper-corrections.json').write_text(json.dumps(changes,indent=2),encoding='utf-8')
print('Corrected actual via drills / fused-input widths:',len(changes))
