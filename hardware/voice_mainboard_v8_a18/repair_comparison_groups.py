"""Connect physical pad groups, avoiding ambiguous airwire track midpoints.

Connectivity is recomputed geometrically after each mutation. A final native
KiCad connectivity/clearance report is the independent acceptance check.
"""
from pathlib import Path
import collections,json,math,os,sys,time
import pcbnew as p
from comparison_route_geometry import b,FILE,route,pos,polys,layers
from shapely.geometry import Polygon,Point,LineString
from shapely.strtree import STRtree
ROOT=FILE.parent; (ROOT/'exports').mkdir(exist_ok=True)

class TrackAnchor:
    def __init__(self, track, endpoint):
        self.position=track.GetStart() if endpoint=='start' else track.GetEnd()
        self.layer=track.GetLayer()
        self.identity=f'{track.m_Uuid.AsString()}:{endpoint}'
    def GetPosition(self):
        return self.position
    def IsOnLayer(self, layer):
        return self.layer==layer

def anchor_key(item):
    return item.identity if isinstance(item,TrackAnchor) else item.m_Uuid.AsString()

def groups(net,orphan_copper=False,exclude_point_contacts=False,add_track_anchors=False):
    pads=[d for f in b.GetFootprints()for d in f.Pads()if d.GetNetname()==net]
    objects=[*pads,*[t for t in b.GetTracks()if t.GetNetname()==net]]
    zones=[]
    for z in b.Zones():
        if z.GetIsRuleArea()or z.GetNetname()!=net:continue
        shape=z.GetFilledPolysList(z.GetLayer())
        for i in range(shape.OutlineCount()):
            q=shape.COutline(i);holes=[]
            for k in range(shape.HoleCount(i)):
                h=shape.CHole(i,k);holes.append([(p.ToMM(h.CPoint(j).x),p.ToMM(h.CPoint(j).y))for j in range(h.PointCount())])
            zones.append((z.GetLayer(),Polygon([(p.ToMM(q.CPoint(j).x),p.ToMM(q.CPoint(j).y))for j in range(q.PointCount())],holes).buffer(0)))
    parent=list(range(len(objects)+len(zones)))
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def join(a,z):parent[find(a)]=find(z)
    for layer in layers:
        shapes=[];owners=[]
        for i,obj in enumerate(objects):
            if not obj.IsOnLayer(layer):continue
            if isinstance(obj,p.PAD):ss=polys(obj,layer)
            elif isinstance(obj,p.PCB_VIA):ss=[Point(pos(obj)).buffer(p.ToMM(obj.GetWidth(layer))/2)]
            else:
                a,z=obj.GetStart(),obj.GetEnd()
                ss=[LineString([(p.ToMM(a.x),p.ToMM(a.y)),(p.ToMM(z.x),p.ToMM(z.y))]).buffer(p.ToMM(obj.GetWidth())/2)]
            shapes.extend(ss);owners.extend([i]*len(ss))
        for j,(zl,sh)in enumerate(zones):
            if zl==layer:shapes.append(sh);owners.append(len(objects)+j)
        if not shapes:continue
        tree=STRtree(shapes)
        for i,sh in enumerate(shapes):
            for j in tree.query(sh):
                if owners[i]!=owners[int(j)]and sh.intersects(shapes[int(j)]):
                    if exclude_point_contacts:
                        contact=sh.intersection(shapes[int(j)])
                        if contact.area<1e-9 and contact.length<1e-6:continue
                    join(owners[i],owners[int(j)])
    result=collections.defaultdict(list)
    for i,d in enumerate(pads):result[find(i)].append(d)
    if orphan_copper:
        pad_roots=set(result)
        return [obj for i,obj in enumerate(objects[len(pads):],start=len(pads)) if find(i) not in pad_roots]
    # An existing narrow pad neck is already electrically connected. Start
    # the broad continuation at its off-pad via rather than attempting to
    # route a wider wire through the narrow neck a second time.
    for i,obj in enumerate(objects[len(pads):],start=len(pads)):
        group=result.get(find(i))
        if group is None:continue
        if isinstance(obj,p.PCB_VIA):group.append(obj)
        elif add_track_anchors:group.extend(TrackAnchor(obj,endpoint) for endpoint in ['start','end'])
    if add_track_anchors:
        for root,group in result.items():
            unique={}
            for item in group:
                key=(*pos(item),tuple(layer for layer in layers if item.IsOnLayer(layer)))
                unique.setdefault(key,item)
            result[root]=list(unique.values())
    return list(result.values())

if __name__=='__main__':
    grid=float(os.environ.get('A18_ROUTE_GRID','.1'))
    report=[];allnets=collections.Counter(d.GetNetname()for f in b.GetFootprints()for d in f.Pads()if d.GetNetname()and not d.GetNetname().startswith('unconnected-'))
    if os.environ.get('A18_ROUTE_RIPUP_SIGNAL_WIRES')=='1' and os.environ.get('A18_LOCK_REPAIRS')=='1':
        # Completed primary buses must survive subsequent local routing.
        # Unfinished buses remain editable until their pad groups are joined.
        priority={'ESP_TX17','ESP_RX18','ESP_DTR4','DEBUG_ESP_TX43','DEBUG_ESP_RX44',
                  'ESP_USB_DP20','ESP_USB_DM19','M_USB_DP','M_USB_DM','MODEM_PWRKEY_N',
                  'I2S_SPK_BCLK15','I2S_SPK_WS16','I2S_SPK_DATA7','I2S_MIC_BCLK14',
                  'I2S_MIC_WS16','I2S_MIC_DATA13','CALL_BOOT0','RESET_CTL','SUPPLY_BAT_N47'}
        complete={net for net in priority if net in allnets and len(groups(net))<2}
        for t in b.GetTracks():
            if t.GetNetname() in complete:t.SetLocked(True)
    # Small local nets first; major rails already have reserved broad paths.
    only=os.environ.get('A18_ONLY_NETS',''); allnets={n:c for n,c in allnets.items() if not only or n in only.split(',')}
    ordered=sorted(allnets,key=lambda n:(n=='GND',n in ['ESP_3V3','SYS_5V','VIN_PROTECTED','BAT_BOOST_5V','MODEM_3V8','BAT_SENSE_IN','CELL_NEG'],allnets[n]))
    for net in ordered:
        failures=set();start=time.monotonic();entry={'net':net,'repairs':[],'failed_searches':[]}
        for attempt in range(30):
            gs=groups(net,add_track_anchors=os.environ.get('A18_ROUTE_ATTACH_TRACK_ENDS')=='1')
            if len(gs)<2:break
            candidates=[]
            for i,g in enumerate(gs):
                for h in gs[i+1:]:
                    for a in g:
                        for z in h:
                            key=tuple(sorted([anchor_key(a),anchor_key(z)]))
                            if key not in failures:candidates.append((math.dist(pos(a),pos(z)),key,a,z))
            if not candidates:break
            ok=False
            prefer_vias=os.environ.get('A18_PREFER_VIA_ENDPOINTS')=='1'
            def attachment_layers(item):
                return {layer for layer in layers if item.IsOnLayer(layer)}
            # A track endpoint and a through via can occupy the same point.
            # At equal distance, retain the via's additional usable layer;
            # selecting the single-layer anchor first can seal a valid route.
            candidate_key=lambda q:((2-int(isinstance(q[2],p.PCB_VIA))-int(isinstance(q[3],p.PCB_VIA))) if prefer_vias else 0,
                                    q[0],-len(attachment_layers(q[2]))-len(attachment_layers(q[3])))
            pair_limit=int(os.environ.get('A18_REPAIR_PAIR_LIMIT','12' if prefer_vias else '6'))
            ordered_pairs=sorted(candidates,key=candidate_key)
            spacing=float(os.environ.get('A18_ROUTE_PAIR_SPACING_MM','0'))
            if spacing>0:
                # Many preserved necks have numerous adjacent short segments.
                # Try distinct attachment regions rather than spending every
                # search on near-identical endpoints inside one blocked pocket.
                diverse=[]
                for pair in ordered_pairs:
                    if any(math.dist(pos(pair[2]),pos(old[2]))<spacing
                           and math.dist(pos(pair[3]),pos(old[3]))<spacing
                           and attachment_layers(pair[2])<=attachment_layers(old[2])
                           and attachment_layers(pair[3])<=attachment_layers(old[3]) for old in diverse):
                        continue
                    diverse.append(pair)
                    if len(diverse)>=pair_limit:break
                ordered_pairs=diverse
            for _,key,a,z in ordered_pairs[:pair_limit]:
                sl={i for i,l in enumerate(layers)if a.IsOnLayer(l)};gl={i for i,l in enumerate(layers)if z.IsOnLayer(l)}
                width=.5 if net in ['VIN_DC','VIN_FUSED']else(.4 if net in ['SPK_PLUS','SPK_MINUS']else(.25 if net in ['ESP_3V3','SYS_5V','VIN_PROTECTED','BAT_BOOST_5V','MODEM_3V8','BAT_SENSE_IN','CELL_NEG']else .16))
                width=float(os.environ.get('A18_REPAIR_WIDTH',width))
                try:
                    pa,pz=pos(a),pos(z)
                    bounds=None if grid>=.1 else(max(.5,min(pa[0],pz[0])-6),max(.5,min(pa[1],pz[1])-6),min(72.5,max(pa[0],pz[0])+6),min(72.5,max(pa[1],pz[1])+6))
                    change=route(net,pa,pz,sl,gl,width=width,step=grid,bounds=bounds)
                    entry['repairs'].append({'from':pos(a),'to':pos(z),'width':width,**change});ok=True
                    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b);break
                except RuntimeError as error:
                    failures.add(key)
                    entry['failed_searches'].append({'from':pos(a),'to':pos(z),'reason':str(error)})
            if not ok:break
        entry.update(remaining_pad_groups=len(groups(net)),seconds=time.monotonic()-start)
        if os.environ.get('A18_LOCK_COMPLETED_NETS')=='1' and entry['remaining_pad_groups']==1:
            # Keep an actually joined signal intact during subsequent rip-up.
            # This applies only to trial routing; native checks still decide
            # whether the resulting complete board can be accepted.
            for t in b.GetTracks():
                if t.GetNetname()==net:t.SetLocked(True)
        report.append(entry);print(net,'repairs',len(entry['repairs']),'groups',entry['remaining_pad_groups'],'seconds',round(entry['seconds'],1),flush=True)
        (ROOT/'exports/pad-group-progress.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    b.BuildConnectivity();assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(FILE),b)
    (ROOT/'exports/pad-group-connections.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
