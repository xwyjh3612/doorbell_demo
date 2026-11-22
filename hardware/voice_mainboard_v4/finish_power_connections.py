"""Use both external copper layers for a checked modem power trunk.

Save actual lengths and trace-only DC drops; do not infer converter, MOSFET,
connector, battery or temperature qualification from a copper connection.
"""
from pathlib import Path
import json,math
import pcbnew as p
ROOT=Path(__file__).resolve().parent;file=ROOT/'voice_mainboard_v4.kicad_pcb'
scope={'__file__':str(ROOT/'connect_two_layers.py')}
exec(compile((ROOT/'connect_two_layers.py').read_text(encoding='utf8').split('d=json.loads')[0],'router','exec'),scope)
r=scope['r'];m=scope['m'];b=r.board;report=[]
for name,xy,layer in [('FEED_A',(42.485,47.65),None),('FEED_Z',(60.8,9.7),None),('BOOST_MAIN',(78.2982,15.3018),p.F_Cu)]:
    r.virtual[name]=r.Endpoint('POWER_BUS',xy)
    r.virtual[name].IsOnLayer=lambda used,layer=layer:layer is None or used==layer
for a,z,width,bounds in [(('FEED_A',0),('FEED_Z',0),.6,(1,1,99,74)),(('C41',1),('BOOST_MAIN',0),.6,(70,1,92,28))]:
    before={t.m_Uuid.AsString()for t in b.GetTracks()}
    try:
        result=m.route(r,a,z,width=width,step=.1,bounds=bounds)
        resistance=0;length=0;vias=0
        for t in b.GetTracks():
            if t.m_Uuid.AsString()in before:continue
            t.SetLocked(True)
            if isinstance(t,p.PCB_VIA):vias+=1;continue
            aa,zz=t.GetStart(),t.GetEnd();mm=math.dist((p.ToMM(aa.x),p.ToMM(aa.y)),(p.ToMM(zz.x),p.ToMM(zz.y)))
            length+=mm;resistance+=1.724e-8*(mm/1000)/(p.ToMM(t.GetWidth())/1000*35e-6)
        report.append({'from':a,'to':z,'connected':True,'width_mm':width,'length_mm':length,'trace_resistance_ohm_at_20C_35um':resistance,'trace_drop_V_at_2A':2*resistance,**result})
    except RuntimeError as e:report.append({'from':a,'to':z,'connected':False,'reason':str(e)})
    p.SaveBoard(str(file),b)
(ROOT/'exports/wide-power-connections.json').write_text(json.dumps({'connections':report,'load_qualified':False,'DC_drop_excludes':['vias','temperature','mux/PFET','connectors','transient']},indent=2)+'\n',encoding='utf8')
print('Power connection results:',report)
