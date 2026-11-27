"""Prepare isolated native KiCad rendering copies; never change PCB copper.

Missing product CAD bodies receive explicitly documented illustrative geometry.
No rendering copy is a fabrication source or a mechanical clearance approval.
"""
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import re
import urllib.request
import pcbnew as p

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
SRC=ROOT/'power_relayout_candidate/voice_mainboard_a18_2layer.kicad_pcb'
OUT=SRC.parent/'exports/3d-preview-20261127'
OUT.mkdir(exist_ok=True)
MODELS=OUT/'models'
MODELS.mkdir(exist_ok=True)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
source_hash=sha(SRC)
lib=REPO/'build/cad-tools/kicad/share/kicad/3dmodels'
extras={
    'F1':'Fuse.3dshapes/Fuse_1812_4532Metric.step',
    'D2':'LED_SMD.3dshapes/LED_WS2812B-2020_PLCC4_2.0x2.0mm.step',
    'J10':'Connector_JAE.3dshapes/JAE_SIM_Card_SF72S006.step',
}
downloads={}
def fetch(pair):
    ref,name=pair
    dest=MODELS/Path(name).name
    url='https://raw.githubusercontent.com/KiCad/kicad-packages3D/master/'+name
    try:
        if not dest.exists():
            request=urllib.request.Request(url,headers={'User-Agent':'VoiceIntercomCADReview/1.0'})
            with urllib.request.urlopen(request,timeout=30)as response:data=response.read(8_000_000)
            assert data.lstrip().startswith(b'ISO-10303-21;'),(ref,'Invalid STEP data')
            dest.write_bytes(data)
        return ref,{'path':dest,'url':url,'sha256':sha(dest),'kind':'KiCad official generic package model'}
    except Exception as error:return ref,{'error':str(error),'url':url}
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:
    downloads.update(pool.map(fetch,extras.items()))

def mesh(vertices,faces,color):
    # KiCad VRML convention is 0.1 inch, convert all body dimensions from mm.
    coords=','.join(' '.join(f'{v/2.54:.8g}'for v in q)for q in vertices)
    indices=','.join(' '.join(str(v)for v in q)+' -1'for q in faces)
    return f'Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} specularColor .25 .25 .25 shininess .4 }} }} geometry IndexedFaceSet {{ solid FALSE coord Coordinate {{ point [ {coords} ] }} coordIndex [ {indices} ] }} }}\n'
def box(x,y,z,w,d,h,color):
    vertices=[(x+dx*w/2,y+dy*d/2,z+dz*h/2)for dz in(-1,1)for dy in(-1,1)for dx in(-1,1)]
    return mesh(vertices,[(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)],color)
def ring(x,y,z,r_outer,r_inner,depth,color):
    n=48
    vertices=[(x+dx,y+r*math.cos(2*math.pi*i/n),z+r*math.sin(2*math.pi*i/n))for dx in(0,depth)for r in(r_outer,r_inner)for i in range(n)]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces += [(i,j,n+j,n+i),(2*n+i,3*n+i,3*n+j,2*n+j),
                  (i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)]
    return mesh(vertices,faces,color)
def custom(ref,content,basis,approx=True):
    dest=MODELS/(ref+'-illustrative.wrl')
    dest.write_text('#VRML V2.0 utf8\n# Illustrated body, not supplier mechanical CAD\n'+content,encoding='utf-8')
    return {'path':dest,'sha256':sha(dest),'kind':'illustrative geometry','basis':basis,'not_for_clearance_validation':approx}

silver='.65 .68 .70'
black='.09 .10 .12'
added={
    'U1':custom('U1',box(0,0,1.1,15.8,17.7,2.2,silver)+box(0,0,2.215,10,12,.03,'.78 .80 .82'),
                'ML307C hardware manual nominal15.8x17.7x2.2mm; simplified shield and label, not exact3D CAD'),
    'U14':custom('U14',box(0,0,.4,3,3,.8,black),'MAX98357A TQFN3x3 outline; simplified height/body'),
    'U18':custom('U18',box(0,0,.3,2.1,1.6,.6,black),'TI DRL0008A simplified body envelope; no lead details'),
    'U17':custom('U17',box(0,0,.5,2.6,2.6,1,black),'XB7608AJL simplified visual body; not verified package CAD'),
    'J1':custom('J1',box(7.1,0,5.5,14.2,9,11,black)+
                ring(-.12,0,5.5,4.05,3.1,.5,silver)+box(.39,0,5.5,.03,6,6,'.03 .03 .03')+
                ring(-.14,0,5.5,1.25,.02,1.6,silver),
                'HX DC005-2.5-T nominal14.2x9x11mm body; mounting-plane/orifice details illustrative'),
}
std=lib/'Package_SO.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm.step'
assert std.exists()
added['U15']={'path':std,'kind':'KiCad generic SOIC8 visual approximation; ESOP exposed pad not modelled','sha256':sha(std)}
for ref,record in downloads.items():
    if 'path'in record:added[ref]=record
    elif ref=='F1':added[ref]=custom(ref,box(0,0,.6,4.5,3.2,1.2,'.16 .36 .14'),'1812 simplified body')
    elif ref=='D2':added[ref]=custom(ref,box(0,0,.45,2,2,.9,'.85 .85 .80'),'2020 LED simplified body')
    else:added[ref]=custom(ref,box(-.98,-1.88,.8,11.4,14.5,1.6,silver),'SIM slot simplified body; origin from footprint outline')

for mode in('assembled','bare'):
    b=p.LoadBoard(str(SRC))
    for f in b.GetFootprints():
        ref=f.GetReference()
        if mode=='bare'or f.IsDNP():f.Models().clear();continue
        # Resolve source-relative paths before moving rendering copy.
        for model in f.Models():
            model.m_Filename=model.m_Filename.replace('${KICAD9_3DMODEL_DIR}',lib.as_posix()).replace('${KIPRJMOD}',SRC.parent.as_posix())
        if ref in added:
            f.Models().clear()
            model=p.FP_3DMODEL()
            model.m_Filename=added[ref]['path'].as_posix()
            model.m_Show=True
            f.Models().push_back(model)
    dest=OUT/(mode+'-render-only.kicad_pcb')
    p.SaveBoard(str(dest),b)
    text=dest.read_text(encoding='utf-8')
    # Render appearance only. Preserve source thickness/copper and do not change
    # production specification. Blue-green mask and silver finish are previews.
    if '(stackup'not in text:
        stack='''(stackup
            (layer "F.SilkS" (type "Top Silk Screen") (color "White"))
            (layer "F.Mask" (type "Top Solder Mask") (color "#087B78"))
            (layer "F.Cu" (type "copper") (thickness 0.035))
            (layer "dielectric 1" (type "core") (thickness 1.13) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
            (layer "B.Cu" (type "copper") (thickness 0.035))
            (layer "B.Mask" (type "Bottom Solder Mask") (color "#087B78"))
            (layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
            (copper_finish "HASL") (dielectric_constraints no))'''
        text=text.replace('(setup','(setup\n'+stack,1)
        dest.write_text(text,encoding='utf-8')
    check=p.LoadBoard(str(dest))
    assert len(list(check.GetFootprints()))==len(list(b.GetFootprints()))==150
    assert len(list(check.GetTracks()))==len(list(b.GetTracks()))
    if mode=='bare':assert all(not len(f.Models())for f in check.GetFootprints())
assert sha(SRC)==source_hash,'Rendering must never modify source PCB'
manifest={'product':'语音对讲主板','source_PCB_sha256':source_hash,'source_PCB':str(SRC.relative_to(REPO)),
    'purpose':'Native KiCad3D preview only, not manufacturing files or collision signoff',
    'DNP_hidden':True,'mask_color':'Blue-green preview only; production mask not changed',
    'added_models':{ref:{key:str(val)if isinstance(val,Path)else val for key,val in data.items()}for ref,data in added.items()},
    'download_records':{ref:{key:str(val)if isinstance(val,Path)else val for key,val in data.items()}for ref,data in downloads.items()}}
(OUT/'3d-preview-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
