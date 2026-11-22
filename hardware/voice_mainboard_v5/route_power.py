"""Place short switch loops and deliberate wide supply routes before autorouting."""
from pathlib import Path
import json, math
import pcbnew as p
from route_support import load
ROOT=Path(__file__).resolve().parent
file=ROOT/'voice_mainboard_v5.kicad_pcb'
r=load()
b=r.board
report=[]


def route(a,z,width=.2,back=False):
    xy,zz=r.pos(r.pad(*a)),r.pos(r.pad(*z))
    margin=5 if width<.6 else 8
    bounds=(max(.6,min(xy[0],zz[0])-margin),max(.6,min(xy[1],zz[1])-margin),min(99.4,max(xy[0],zz[0])+margin),min(74.4,max(xy[1],zz[1])+margin))
    count=len(report)
    before={t.m_Uuid.AsString() for t in b.GetTracks()}
    try:
        if not back:
            r.route(a,z,width=width,step=.05,bounds=bounds)
        else:
            av,zv=f'PWR_A_{count}',f'PWR_Z_{count}'
            r.escapevia(av,a,diameter=.8,drill=.4,neck=min(width,.4))
            r.escapevia(zv,z,diameter=.8,drill=.4,neck=min(width,.4))
            r.route((av,0),(zv,0),layer=p.B_Cu,width=width,step=.1,bounds=bounds)
        added=[t for t in b.GetTracks() if t.m_Uuid.AsString() not in before]
        for t in added:t.SetLocked(True)
        length=resistance=0
        for t in added:
            if isinstance(t,p.PCB_VIA):continue
            axy,zxy=t.GetStart(),t.GetEnd()
            segment=math.dist((p.ToMM(axy.x),p.ToMM(axy.y)),(p.ToMM(zxy.x),p.ToMM(zxy.y)))
            length+=segment
            resistance+=1.724e-8*(segment/1000)/(p.ToMM(t.GetWidth())/1000*35e-6)
        report.append({'from':a,'to':z,'net':r.pad(*a).GetNetname(),'width_mm':width,'back_trunk':back,'connected':True,
            'added_copper_items':len(added), 'added_trace_length_mm':length,
            'added_trace_resistance_sum_ohm_20C_35um':resistance,
            'added_track_uuids':[t.m_Uuid.AsString() for t in added],
            'resistance_limits':'Sum of added trace segments only; excludes vias/pads/connectors/ICs/temperature. Not a whole-board end-to-end resistance or current rating.'})
    except (RuntimeError, AssertionError) as e:
        report.append({'from':a,'to':z,'net':r.pad(*a).GetNetname(),'width_mm':width,'back_trunk':back,'connected':False,'reason':str(e)})
    p.SaveBoard(str(file),b)


for a,z,w in [
    (('U2',2),('L1',1),.5), (('U2',3),('C4',1),.5),
    (('U2',6),('C3',1),.2), (('C3',2),('U2',2),.2),
    (('U2',4),('R2',2),.2), (('R2',2),('R3',1),.2),
    (('U2',5),('R1',2),.2),
    (('L1',2),('C6',1),.8), (('C6',1),('C7',1),.8),
    (('C10',1),('U1',43),.55), (('U1',43),('U1',42),.55),
    (('U13',4),('C59',1),.4), (('U13',1),('C59',1),.3),
    (('U13',5),('R60',1),.2), (('R60',1),('R59',2),.2),
    (('U13',5),('C63',2),.2), (('R59',1),('C63',1),.2),
    (('U14',7),('U14',8),.2), (('U14',8),('C61',1),.4),
]:route(a,z,w)

for a,z,w in [
    (('C7',1),('C10',1),1.0),
    (('U15',3),('C8',1),1.2),
    (('C8',1),('C4',1),.8),
    (('U15',3),('C59',1),.8),
    (('U15',3),('C61',1),.8),
    (('Q6',2),('U15',1),1.0),
]:route(a,z,w,back=True)

(ROOT/'exports/critical-power-routes.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('Critical connections',sum(x['connected'] for x in report),'/',len(report))
