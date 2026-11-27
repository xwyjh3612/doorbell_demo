"""Restore selected saved copper, without loading two projects in one process.

Only copper is restored. Pad geometry, positions and connectivity contracts
remain those of the current board. A new native DRC is mandatory afterwards.
"""
import datetime,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from comparison_route_geometry import b,FILE,p

source=Path(os.environ['A18_RESTORE_SOURCE']).resolve()
net=os.environ['A18_RESTORE_NET']
extract=r'''
import json,sys,pcbnew as p
b=p.LoadBoard(sys.argv[1]);out=[]
for t in b.GetTracks():
 if t.GetNetname()!=sys.argv[2]:continue
 q={'via':isinstance(t,p.PCB_VIA),'locked':t.IsLocked()}
 if q['via']:q.update(x=t.GetPosition().x,y=t.GetPosition().y,width=t.GetWidth(p.F_Cu),drill=t.GetDrill(),kind=t.GetViaType())
 else:q.update(ax=t.GetStart().x,ay=t.GetStart().y,zx=t.GetEnd().x,zy=t.GetEnd().y,width=t.GetWidth(),layer=t.GetLayer())
 out.append(q)
print(json.dumps(out))
'''
records=json.loads(subprocess.run([sys.executable,'-c',extract,str(source),net],check=True,capture_output=True,text=True).stdout)
assert records
snapshot=FILE.parent/'iterations'/('before-net-restore-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snapshot.mkdir(parents=True);shutil.copy2(FILE,snapshot/FILE.name)
held=[]
for t in list(b.GetTracks()):
 if t.GetNetname()==net:
  held.append(t);b.Remove(t)
 if os.environ.get('A18_REMOVE_BUTTON_GROUND')=='1' and t.GetNetname()=='GND' and not isinstance(t,p.PCB_VIA):
  ends={(t.GetStart().x,t.GetStart().y),(t.GetEnd().x,t.GetEnd().y)}
  if ends=={(p.FromMM(39.65),p.FromMM(38.4)),(p.FromMM(33.35),p.FromMM(38.4))}:
   held.append(t);b.Remove(t)
 if os.environ.get('A18_REMOVE_OUTPUT_CAP_GROUND')=='1' and t.GetNetname()=='GND' and not isinstance(t,p.PCB_VIA):
  ends={(t.GetStart().x,t.GetStart().y),(t.GetEnd().x,t.GetEnd().y)}
  wanted=[{(p.FromMM(37.2),p.FromMM(52)),(p.FromMM(37.2),p.FromMM(53.2))},{(p.FromMM(37.2),p.FromMM(53.2)),(p.FromMM(33.5),p.FromMM(53.2))}]
  if ends in wanted:held.append(t);b.Remove(t)
for t in records:
 if t['via']:
  q=p.PCB_VIA(b);q.SetPosition(p.VECTOR2I(t['x'],t['y']));q.SetWidth(t['width']);q.SetDrill(t['drill']);q.SetLayerPair(p.F_Cu,p.B_Cu);q.SetViaType(t['kind'])
 else:
  q=p.PCB_TRACK(b);q.SetStart(p.VECTOR2I(t['ax'],t['ay']));q.SetEnd(p.VECTOR2I(t['zx'],t['zy']));q.SetWidth(t['width']);q.SetLayer(t['layer'])
 q.SetLocked(t['locked']);q.SetNetCode(b.FindNet(net).GetNetCode());b.Add(q)
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
report={'net':net,'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'restored_tracks_vias':len(records),'retired_tracks_vias':len(held),'snapshot':str(snapshot),'native_DRC_required':True}
(FILE.parent/'exports'/('restored-'+net+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
for t in held:t.thisown=False
print(json.dumps(report,indent=2))
