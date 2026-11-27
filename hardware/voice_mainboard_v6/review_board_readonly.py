"""Measure the saved board without saving/rebuilding any CAD file."""
import collections
import hashlib
import json
import math
from pathlib import Path
import pcbnew as p

ROOT = Path(__file__).resolve().parent
PCB = ROOT / 'voice_mainboard_v6.kicad_pcb'
OUT = ROOT / 'exports/engineering-review-20261124'
OUT.mkdir(parents=True, exist_ok=True)
before = hashlib.sha256(PCB.read_bytes()).hexdigest()
b = p.LoadBoard(str(PCB))
d = json.loads((ROOT / 'design.json').read_text(encoding='utf-8'))
parts = {q['ref']:q for q in d['parts']}
fps = {f.GetReference():f for f in b.GetFootprints()}

def xy(point):
    return [round(p.ToMM(point.x), 4), round(p.ToMM(point.y), 4)]

def pad(ref, number):
    return next(a for a in fps[ref].Pads() if a.GetNumber()==str(number))

def gap(a, z):
    pa, pz = pad(*a), pad(*z)
    ap, zp = xy(pa.GetPosition()), xy(pz.GetPosition())
    return {'from':list(a),'to':list(z),'pad_center_distance_mm':round(math.dist(ap,zp),4),
            'from_xy':ap,'to_xy':zp,'net_from':pa.GetNetname(),'net_to':pz.GetNetname(),
            'scope':'Pad center straight-line distance; not loop inductance, routed path or pass/fail threshold.'}

measurements = [
    (('U2',4),('C4',1)),(('U2',3),('L1',1)),(('U13',4),('C59',1)),(('U13',3),('L5',1)),
    (('U15',4),('C64',1)),(('U15',3),('L4',2)),(('U15',7),('C65',1)),(('U15',7),('C66',1)),
    (('U18',3),('C71',1)),(('U18',6),('C73',1)),(('U18',2),('C72',1)),
    (('U16',4),('C67',1)),(('U16',5),('C68',1)),(('U14',7),('C61',1)),(('U14',7),('C62',1)),
    (('U7',2),('C57',1)),(('U1',42),('C8',1)),(('U1',35),('J11',1)),
    (('U7',8),('U14',16)),(('U7',9),('U14',14)),(('U7',7),('U14',1)),
]
tracks=collections.defaultdict(list)
for t in b.GetTracks():
    rec={'uuid':t.m_Uuid.AsString(),'layer':b.GetLayerName(t.GetLayer()),'start':xy(t.GetStart()),'end':xy(t.GetEnd())}
    if isinstance(t,p.PCB_VIA):
        rec.update(kind='via',diameter_mm=p.ToMM(t.GetWidth(p.F_Cu)),drill_mm=p.ToMM(t.GetDrillValue()))
    else:
        rec.update(kind='track',width_mm=p.ToMM(t.GetWidth()),length_mm=p.ToMM(t.GetLength()))
    tracks[t.GetNetname()].append(rec)
selected=['VIN_DC','VIN_FUSED','VIN_PROTECTED','SYS_5V','BAT_SENSE_IN','CELL_NEG','BAT_BOOST_5V','MODEM_3V8','ESP_3V3','UPS_SW','BUCK_SW','ESP_SW','RF_ANT', 'RF_MODULE','M_USB_DP','M_USB_DM','ESP_USB_DP20','ESP_USB_DM19','SERVICE_USB_DP','SERVICE_USB_DM','I2S_SPK_BCLK15','I2S_SPK_WS16','I2S_SPK_DATA7']
net_stats={}
for name in selected:
    ts=tracks[name];segments=[t for t in ts if t['kind']=='track'];vias=[t for t in ts if t['kind']=='via']
    zs=[z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname()==name]
    net_stats[name]={'sum_track_length_mm':round(sum(t['length_mm'] for t in segments),3),
                     'width_histogram_mm':dict(collections.Counter(t['width_mm'] for t in segments)),
                     'via_count':len(vias),'zones':[{'layer':b.GetLayerName(z.GetLayer()),'bbox_mm':{'x':p.ToMM(z.GetBoundingBox().GetX()),'y':p.ToMM(z.GetBoundingBox().GetY()),'w':p.ToMM(z.GetBoundingBox().GetWidth()),'h':p.ToMM(z.GetBoundingBox().GetHeight())}} for z in zs],
                     'items':ts,'scope':'Sum of all branches, not a measured current path. Copper pours not represented by track width.'}

groups=collections.defaultdict(list)
for q in d['parts']:
    if q['kind']=='pcb' and not q['dnp'] and not q['ref'].startswith('TP'):
        groups[q['group']].append(q['ref'])
counts=collections.Counter('THT' if fps[q['ref']].GetAttributes() & p.FP_THROUGH_HOLE else 'SMT' for q in d['parts'] if q['kind']=='pcb' and not q['dnp'] and not q['ref'].startswith('TP'))
result={'date':'2026-11-24','PCB_sha256':before,'read_only':True,'populated_count':sum(counts.values()),
        'population_by_attribute':dict(counts),'groups':dict(groups),'pad_distances':[gap(a,z) for a,z in measurements],
        'net_geometry':net_stats,'power_pin_necks':{},'simulation_of_hardware':False,'manufacturing_ready':False}
for ref,n in [('U18',2),('U18',7),('U15',4),('U15',7),('U17',2),('U17',3),('U17',4),('U17',5),('U2',4),('U13',4)]:
    pd=pad(ref,n)
    result['power_pin_necks'][f'{ref}.{n}']={'position_mm':xy(pd.GetPosition()),'pad_size_mm':xy(pd.GetSize()),'net':pd.GetNetname()}
after=hashlib.sha256(PCB.read_bytes()).hexdigest()
assert before==after, 'Read-only review modified CAD unexpectedly'
(OUT/'geometry-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'sha256':before,'counts':dict(counts),'distances':result['pad_distances'],
                  'net_summary':{k:{a:z for a,z in v.items() if a not in ['items','zones','scope']} for k,v in net_stats.items() if v['items']}},ensure_ascii=False,indent=2))
