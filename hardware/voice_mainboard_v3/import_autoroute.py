"""Import a router session onto its original board and report preserved copper."""
from pathlib import Path
import pcbnew as p,json,sys,shutil
root=Path(__file__).resolve().parent
boardfile=root/'voice_mainboard_v3.kicad_pcb'
session=Path(sys.argv[1])
b=p.LoadBoard(str(boardfile))
def geometry(t):
    if isinstance(t,p.PCB_VIA):return ('via',t.GetNetname(),t.GetPosition().x,t.GetPosition().y,t.GetWidth(p.F_Cu),t.GetDrill())
    return ('track',t.GetNetname(),t.GetLayer(),t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth())
critical={'UPS_SW','UPS_CBST','BUCK_SW','SYS_SW','USB_HOST_DP','USB_HOST_DM','RF_ANT','ANT_MATCH','MODEM_3V8'}
before={geometry(t)for t in b.GetTracks()if t.GetNetname()in critical}
shutil.copy2(boardfile,'build/voice-v3-before-ses.kicad_pcb')
assert p.ImportSpecctraSES(b,str(session))
after={geometry(t)for t in b.GetTracks()if t.GetNetname()in critical}
# Session files may split an existing straight segment; record, do not infer
# equivalence merely from total net length. Review DRC and the critical loop.
assert p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(str(boardfile),b)
(root/'exports/session-import.json').write_text(json.dumps({'session':session.name,'tracks_and_vias':len(list(b.GetTracks())),
 'critical_exact_geometry_before':len(before),'critical_exact_geometry_after':len(after),'critical_original_geometry_missing_count':len(before-after),'manufacturing_ready':False},indent=2)+'\n',encoding='utf8')
print('Imported session:',len(list(b.GetTracks())),'copper items; original critical segments changed:',len(before-after))
