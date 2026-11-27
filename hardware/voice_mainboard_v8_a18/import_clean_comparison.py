"""Import only into an isolated comparison and rebuild explicit ground planes."""
from pathlib import Path
import sys,json,shutil
import pcbnew as p
ROOT=Path(__file__).resolve().parent
count=int(sys.argv[1]);assert count in [2,4]
OUT=ROOT/f'comparison_clean_{count}layer';NAME=f'voice_mainboard_a18_clean_{count}layer'
file=OUT/(NAME+'.kicad_pcb')
shutil.copy2(file,OUT/'placement-before-routing.kicad_pcb')
b=p.LoadBoard(str(file));assert b.GetCopperLayerCount()==count
assert p.ImportSpecctraSES(b,str(OUT/'clean.ses'))
data=json.loads((OUT/'design.json').read_text(encoding='utf-8'))
for layer in [p.F_Cu,p.B_Cu]+([p.In1_Cu]if count==4 else[]):
    z=p.ZONE(b);z.SetLayer(layer);z.SetNet(b.FindNet('GND'))
    z.SetLocalClearance(p.FromMM(.2));z.SetMinThickness(p.FromMM(.2))
    z.SetPadConnection(p.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    z.Outline().NewOutline()
    for x,y in data['mechanical']['outline_mm']:z.Outline().Append(p.FromMM(x),p.FromMM(y))
    b.Add(z)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(file),b)
print('Imported comparison and filled ground; native DRC still required',count,flush=True)
