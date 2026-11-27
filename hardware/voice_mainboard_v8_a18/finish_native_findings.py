"""Fix native edge findings and preserve an explicitly customized U.FL keepout.

The U.FL pad geometry is unchanged. The four-layer library variant records its
active-copper-layer keepout rather than excluding the native mismatch warning.
"""
from pathlib import Path
import json,os,math
import pcbnew as p
from comparison_route_geometry import b,FILE,route,layers
ROOT=FILE.parent;SOURCE=Path(__file__).resolve().parent
report=json.loads(Path(os.environ['A18_FINISH_DRC']).read_text(encoding='utf-8'))
tracks={str(t.m_Uuid.AsString()):t for t in b.GetTracks()};held=[];changes=[]
for q in report['violations']:
    if q['type']!='copper_edge_clearance':continue
    t=next((tracks[i['uuid']]for i in q['items']if i['uuid']in tracks),None)
    if t is None or isinstance(t,p.PCB_VIA):continue
    a,z=t.GetStart(),t.GetEnd();pa=(p.ToMM(a.x),p.ToMM(a.y));pz=(p.ToMM(z.x),p.ToMM(z.y));net=t.GetNetname();layer=t.GetLayer()
    held.append(t);b.Remove(t)
    try:
        bounds=(max(.5,min(pa[0],pz[0])-4),max(.5,min(pa[1],pz[1])-4),min(72.5,max(pa[0],pz[0])+4),min(72.5,max(pa[1],pz[1])+4))
        result=route(net,pa,pz,{layers.index(layer)},{layers.index(layer)},width=.16,step=.05,bounds=bounds)
        changes.append({'edge_reroute':net,'success':True,**result})
    except RuntimeError as error:
        b.Add(t);held.remove(t);changes.append({'edge_reroute':net,'success':False,'reason':str(error)})
if b.GetCopperLayerCount()==4:
    f=next(f for f in b.GetFootprints()if f.GetReference()=='J11')
    name='UFL_Hirose_Active4Layer_A18'
    template=p.FootprintLoad(str(SOURCE.parents[1]/'build/cad-tools/kicad/share/kicad/footprints/Connector_Coaxial.pretty'),'U.FL_Hirose_U.FL-R-SMT-1_Vertical')
    mask=p.LSET()
    for layer in layers:mask.AddLayer(layer)
    for zone in template.Zones():zone.SetLayerSet(mask)
    template.SetFPID(p.LIB_ID('VoiceV2',name))
    p.FootprintSave(str(SOURCE/'VoiceV2.pretty'),template)
    assert (SOURCE/'VoiceV2.pretty'/(name+'.kicad_mod')).exists()
    replacement=p.FootprintLoad(str(SOURCE/'VoiceV2.pretty'),name)
    replacement.SetFPID(p.LIB_ID('VoiceV2',name));replacement.SetPosition(f.GetPosition());replacement.SetOrientationDegrees(f.GetOrientationDegrees())
    oldpads=sorted((d.GetNumber(),d.GetPosition().x,d.GetPosition().y,d.GetSize().x,d.GetSize().y)for d in f.Pads())
    newpads=sorted((d.GetNumber(),d.GetPosition().x,d.GetPosition().y,d.GetSize().x,d.GetSize().y)for d in replacement.Pads())
    assert oldpads==newpads,'U.FL replacement may not change pad geometry'
    replacement.SetReference(f.GetReference());replacement.SetValue(f.GetValue());replacement.SetPath(f.GetPath())
    for field,newfield in [(f.Reference(),replacement.Reference()),(f.Value(),replacement.Value())]:
        newfield.SetLayer(field.GetLayer());newfield.SetPosition(field.GetPosition());newfield.SetTextSize(field.GetTextSize());newfield.SetTextThickness(field.GetTextThickness());newfield.SetVisible(field.IsVisible())
    for d in replacement.Pads():d.SetNet(b.FindNet('RF_FEED' if d.GetNumber()=='1' else 'GND'))
    b.Remove(f);held.append(f);b.Add(replacement)
    design=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
    q=next(q for q in design['parts']if q['ref']=='J11');q['footprint']='VoiceV2:'+name
    q['note']=q.get('note','')+' A18 library variant records keepout on F/B/In1/In2; Hirose pad geometry is unchanged.'
    (ROOT/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2),encoding='utf-8')
    sch=FILE.with_suffix('.kicad_sch');text=sch.read_text(encoding='utf-8')
    oldname='Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical'
    text=text.replace('VoiceV2:'+name,oldname)
    # Override only the placed symbol; keep the embedded library default intact.
    at=text.rindex(oldname);text=text[:at]+'VoiceV2:'+name+text[at+len(oldname):]
    sch.write_text(text,encoding='utf-8')
    changes.append({'library_variant':name,'pads_unchanged':True,'purpose':'active four-layer copper keepout recorded in library'})
b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
(ROOT/'exports/native-findings-fixes.json').write_text(json.dumps(changes,indent=2),encoding='utf-8')
print(json.dumps(changes,indent=2))
for t in held:t.thisown=False
