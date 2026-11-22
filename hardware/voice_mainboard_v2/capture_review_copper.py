"""Save independently checked copper for deterministic KiCad regeneration.

This preserves engineering geometry, not a manufacturing approval. Run with
KiCad Python and explicitly provide a board and its CLI DRC JSON report.
"""
from pathlib import Path
import sys,json,hashlib
import pcbnew as pcb
from restore_review_routes import signature
ROOT=Path(__file__).resolve().parent
source,report=map(Path,sys.argv[1:3])
checks=json.loads(report.read_text(encoding='utf-8'))
assert not checks['violations'] and not checks['unconnected_items'],'Copper must pass full DRC including connectivity'
board=pcb.LoadBoard(str(source))
design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
actual={(fp.GetReference(),pd.GetNumber()):pd.GetNetname()for fp in board.GetFootprints()for pd in fp.Pads()if pd.GetNetname()}
expected={(part['ref'],number):net for part in design['parts']for number,net in part['pins'].items()if net}
assert actual==expected,'Captured board has a different pad/net contract'
for part in design['parts']:
    fp=next(fp for fp in board.GetFootprints()if fp.GetReference()==part['ref'])
    assert abs(pcb.ToMM(fp.GetPosition().x)-part['x'])<1e-6 and abs(pcb.ToMM(fp.GetPosition().y)-part['y'])<1e-6
    assert abs((fp.GetOrientationDegrees()-part['angle']+180)%360-180)<1e-6,part['ref']+' orientation changed'
def point(p):return [p.x,p.y]
tracks=[]
for item in board.GetTracks():
    assert not isinstance(item,pcb.PCB_ARC),'Arc preservation must be implemented before capture'
    if isinstance(item,pcb.PCB_VIA):
        tracks.append(dict(type='via',net=item.GetNetname(),position_nm=point(item.GetPosition()),width_nm=item.GetWidth(pcb.F_Cu),drill_nm=item.GetDrill(),is_free=item.GetIsFree()))
    else:
        tracks.append(dict(type='track',net=item.GetNetname(),start_nm=point(item.GetStart()),end_nm=point(item.GetEnd()),width_nm=item.GetWidth(),layer=board.GetLayerName(item.GetLayer())))
zones=[]
for zone in board.Zones():
    outline=zone.Outline()
    assert outline.OutlineCount()==1 and outline.HoleCount(0)==0,'Complex zone preservation not implemented'
    ch=outline.COutline(0)
    zones.append(dict(net=zone.GetNetname(),layer=board.GetLayerName(zone.GetLayer()),outline_nm=[point(ch.CPoint(i))for i in range(ch.PointCount())],priority=zone.GetAssignedPriority(),clearance_nm=zone.GetLocalClearance(),minimum_thickness_nm=zone.GetMinThickness(),pad_connection=int(zone.GetPadConnection()),island_removal=int(zone.GetIslandRemovalMode()),min_island_area_nm2=zone.GetMinIslandArea()))
directory=ROOT/'routing';directory.mkdir(exist_ok=True)
copper=directory/'review-copper.json'
copper.write_text(json.dumps(dict(tracks=tracks,zones=zones),separators=(',',':'))+'\n',encoding='utf-8')
metadata=dict(status='CONNECTED_ENGINEERING_REVIEW_NOT_FOR_FABRICATION',placement_net_signature=signature(design),copper_sha256=hashlib.sha256(copper.read_bytes()).hexdigest(),source_board_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_drc_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),drc_violations=0,unconnected=0,kicad_version=pcb.Version(),copper_items=len(tracks),zones=len(zones),reference_layer='In1.Cu: no signal traces',minimum_via_diameter_mm=.45,minimum_through_drill_mm=.2,minimum_via_annular_ring_mm=.125,power_rf_usb_review_complete=False,manufacturing_ready=False)
(directory/'review-copper-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
print('Captured',len(tracks),'copper items and',len(zones),'zones; manufacturing review still required.')
