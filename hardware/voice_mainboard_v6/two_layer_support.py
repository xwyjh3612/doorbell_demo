"""Reuse the geometric search constrained to two layers and native keepouts."""
from pathlib import Path
import types
from route_support import load as load_basic
ROOT=Path(__file__).resolve().parent


def load():
    r=load_basic()
    source=(ROOT.parent/'voice_mainboard_v3/route_multilayer.py').read_text(encoding='utf8')
    source=source.replace('layers=[p.F_Cu,p.B_Cu,p.In2_Cu]','layers=[p.F_Cu,p.B_Cu]').replace('range(3)','range(len(layers))')
    source=source.replace('from shapely.geometry import Point,LineString','from shapely.geometry import Point,LineString,Polygon')
    # A rounded goal grid cell can be blocked while the exact pad/via center is
    # clear. Accept nearby clear cells with a checked final segment to the real
    # endpoint; preserve that final bend instead of replacing the snapped node.
    source=source.replace('    costs={};parent={};heap=[];visited=0;found=None','''    goal_nodes=set()
    for k in goal_layers:
        for tx in range(max(0,gx-3),min(len(xs),gx+4)):
            for ty in range(max(0,gy-3),min(len(ys),gy+4)):
                point=(float(xs[tx]),float(ys[ty]))
                if not grids[k][ty,tx] and not obstacles[k].intersects(LineString([point,goal])):
                    goal_nodes.add((tx,ty,k))
    costs={};parent={};heap=[];visited=0;found=None''')
    source=source.replace('if(x,y)==(gx,gy)and li in goal_layers:found=node;break','if node in goal_nodes:found=node;break')
    source=source.replace("zz=goal if(tx,ty)==(gx,gy)else(float(xs[tx]),float(ys[ty]))", "zz=(float(xs[tx]),float(ys[ty]))")
    source=source.replace('current[-1]=goal;groups.append((li,current))', 'current.append(goal);groups.append((li,current))')
    source=source.replace('        shapes=[]','''        shapes=[]
        for zone in [*b.Zones(),*[z for f in b.GetFootprints()for z in f.Zones()]]:
            if not zone.GetIsRuleArea() or not zone.IsOnLayer(layer):continue
            for zi in range(zone.Outline().OutlineCount()):
                ring=zone.Outline().COutline(zi)
                pts=[(p.ToMM(ring.CPoint(j).x),p.ToMM(ring.CPoint(j).y))for j in range(ring.PointCount())]
                if len(pts)>2:
                    sh=Polygon(pts);shapes.append(sh.buffer(clearance));via_obstacles.append(sh.buffer(.505))''')
    m=types.ModuleType('v5_two_layer_search')
    exec(compile(source,'v5_two_layer_search','exec'),m.__dict__)
    return r,m
