"""Measure ground-reference coverage under the paired USB trace portion.

Coverage is a layout observation, not an eye-diagram or impedance measurement.
"""
from pathlib import Path
import json,sys,math
import pcbnew as pcb
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'build/cad-tools/route-python'))
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union

board_path=Path(sys.argv[3])if len(sys.argv)>3 else ROOT/'voice_mainboard_v2.kicad_pcb'
b=pcb.LoadBoard(str(board_path))
signal_layer=b.GetLayerID(sys.argv[1] if len(sys.argv)>1 else 'F.Cu')
reference_layer=b.GetLayerID(sys.argv[2] if len(sys.argv)>2 else 'In1.Cu')
def points(chain):
    return [(pcb.ToMM(chain.CPoint(i).x),pcb.ToMM(chain.CPoint(i).y))for i in range(chain.PointCount())]
polys=[]
for zone in b.Zones():
    if zone.GetNetname()!='GND' or zone.GetLayer()!=reference_layer:continue
    filled=zone.GetFilledPolysList(reference_layer)
    for i in range(filled.OutlineCount()):
        holes=[points(filled.CHole(i,j))for j in range(filled.HoleCount(i))]
        polys.append(Polygon(points(filled.COutline(i)),holes))
reference=unary_union(polys)
lines={n:[] for n in ['ESP_USB_DM19','ESP_USB_DP20']}
for t in b.GetTracks():
    if isinstance(t,pcb.PCB_VIA)or t.GetLayer()!=signal_layer or t.GetNetname()not in lines:continue
    a,z=t.GetStart(),t.GetEnd()
    lines[t.GetNetname()].append(LineString([(pcb.ToMM(a.x),pcb.ToMM(a.y)),(pcb.ToMM(z.x),pcb.ToMM(z.y))]))
unions={n:unary_union(v)for n,v in lines.items()}
checks=[]
for name,paths in lines.items():
    other=unions['ESP_USB_DP20'if name=='ESP_USB_DM19'else'ESP_USB_DM19']
    paired=covered=0.0;breaks=[]
    for line in paths:
        count=max(1,math.ceil(line.length/.025));step=line.length/count
        for i in range(count):
            point=line.interpolate((i+.5)*step)
            if not .47<=point.distance(other)<=.53:continue
            paired+=step
            if reference.covers(point):covered+=step
            else:breaks.append([round(point.x,3),round(point.y,3)])
    checks.append(dict(net=name,paired_sampled_length_mm=paired,
                       reference_covered_length_mm=covered,
                       reference_coverage_percent=100*covered/paired if paired else 0,
                       samples_outside_reference=breaks))
result=dict(method='KiCad filled ground polygons; 0.025mm centreline samples',
            signal_layer=b.GetLayerName(signal_layer),reference_layer=b.GetLayerName(reference_layer),
            checks=checks,reference_plane_continuous_under_paired_traces=all(not q['samples_outside_reference']for q in checks),
            purpose='Locate reference-plane interruptions for engineering review',
            actual_usb_eye_test_passed=False,measured_impedance=False)
(ROOT/'exports/usb-reference-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps({q['net']:round(q['reference_coverage_percent'],2)for q in checks}))
