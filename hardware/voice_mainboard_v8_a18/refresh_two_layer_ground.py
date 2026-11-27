"""Refill ground against the actual project net classes and process rules."""
from pathlib import Path
import datetime,json,shutil
import pcbnew as p
from comparison_route_geometry import b,FILE,net_clearance

snap=FILE.parent/'iterations'/('before-ground-refill-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snap.mkdir(parents=True);shutil.copy2(FILE,snap/FILE.name)
for z in b.Zones():
    if not z.GetIsRuleArea()and z.GetNetname()=='GND':
        z.SetLocalClearance(p.FromMM(net_clearance('GND')))
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
report={'default_ground_clearance_mm':net_clearance('GND'),'actual_project_bound':True,
        'track_and_via_sizes_reset':False,'no_DRC_exclusions_added':True,'native_DRC_required':True}
(FILE.parent/'exports/project-ground-refill.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Refilled ground with actual project classes; no track/via size reset.')
