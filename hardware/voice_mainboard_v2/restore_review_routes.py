"""Restore reviewed router geometry only when the placement/net contract matches.

This preserves reproducibility across regenerated KiCad UUIDs. Copper restored
here is still subject to DRC and power/RF/USB review; no fabrication approval.
"""
from pathlib import Path
import json,hashlib
import pcbnew as pcb
ROOT=Path(__file__).resolve().parent

def signature(design):
    contract=[{k:p[k] for k in ['ref','footprint','x','y','angle','pins']}
              for p in sorted(design['parts'],key=lambda p:p['ref'])]
    raw=json.dumps(contract,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(raw).hexdigest()

if __name__=='__main__':
    copper=ROOT/'routing/review-copper.json'
    copper_meta=ROOT/'routing/review-copper-metadata.json'
    ses=ROOT/'routing/review-route.ses'
    meta=ROOT/'routing/review-route.json'
    if copper.exists() and copper_meta.exists():
        design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
        evidence=json.loads(copper_meta.read_text(encoding='utf-8'))
        assert signature(design)==evidence['placement_net_signature'],'Saved copper is stale; reroute changed design'
        assert hashlib.sha256(copper.read_bytes()).hexdigest()==evidence['copper_sha256'],'Saved copper changed without a review record'
        geometry=json.loads(copper.read_text(encoding='utf-8'))
        board=pcb.LoadBoard(str(ROOT/'voice_mainboard_v2.kicad_pcb'))
        assert not list(board.GetTracks()) and not list(board.Zones()),'Restore onto a fresh generated board'
        for item in geometry['tracks']:
            if item['type']=='via':
                track=pcb.PCB_VIA(board);track.SetPosition(pcb.VECTOR2I(*item['position_nm']))
                track.SetWidth(item['width_nm']);track.SetDrill(item['drill_nm'])
                track.SetViaType(pcb.VIATYPE_THROUGH);track.SetLayerPair(pcb.F_Cu,pcb.B_Cu)
                track.SetIsFree(item.get('is_free',False))
            else:
                track=pcb.PCB_TRACK(board);track.SetStart(pcb.VECTOR2I(*item['start_nm']))
                track.SetEnd(pcb.VECTOR2I(*item['end_nm']));track.SetWidth(item['width_nm'])
                track.SetLayer(board.GetLayerID(item['layer']))
            track.SetNetCode(board.FindNet(item['net']).GetNetCode());track.SetLocked(True);board.Add(track)
        for item in geometry['zones']:
            zone=pcb.ZONE(board);zone.SetLayer(board.GetLayerID(item['layer']))
            zone.SetNetCode(board.FindNet(item['net']).GetNetCode());zone.SetLocalClearance(item['clearance_nm'])
            zone.SetMinThickness(item['minimum_thickness_nm']);zone.SetAssignedPriority(item['priority'])
            zone.SetPadConnection(item['pad_connection']);zone.SetIslandRemovalMode(item['island_removal'])
            zone.SetMinIslandArea(item['min_island_area_nm2']);outline=zone.Outline();outline.NewOutline()
            for x,y in item['outline_nm']:outline.Append(x,y)
            board.Add(zone)
        board.BuildConnectivity();assert pcb.ZONE_FILLER(board).Fill(board.Zones()),'Restored plane fill failed'
        pcb.SaveBoard(str(ROOT/'voice_mainboard_v2.kicad_pcb'),board)
        print('Restored connected engineering copper:',len(geometry['tracks']),'items; manufacturing not approved.')
    elif not ses.exists() or not meta.exists():
        print('No additional saved review routes; local branches retained.')
    else:
        design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
        evidence=json.loads(meta.read_text(encoding='utf-8'))
        assert signature(design)==evidence['placement_net_signature'],'Saved routing is stale; reroute changed design'
        assert hashlib.sha256(ses.read_bytes()).hexdigest()==evidence['ses_sha256'],'Saved SES was modified without a review record'
        board=pcb.LoadBoard(str(ROOT/'voice_mainboard_v2.kicad_pcb'))
        assert pcb.ImportSpecctraSES(board,str(ses)),'KiCad SES import failed'
        pcb.SaveBoard(str(ROOT/'voice_mainboard_v2.kicad_pcb'),board)
        print('Restored additional review routes:',len(list(board.GetTracks())),'copper items; manufacturing not approved.')
