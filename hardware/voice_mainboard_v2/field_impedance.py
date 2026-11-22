"""Quasi-static 2D field estimate for the RF grounded coplanar cross-section.

This solves electrostatic capacitance with finite volumes, then uses an air
reference to estimate quasi-TEM impedance. It is not a 3D antenna simulation,
USB eye test, material characterization, or fabrication impedance measurement.
"""
from pathlib import Path
import json, time
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

ROOT = Path(__file__).resolve().parent
EPS0 = 8.8541878128e-12
C = 299792458.0

def capacitance(width=.32, height=.18, gap=.2, copper=.035, er=4.2,
                mask=.01, mask_er=3.5, dx=.005, span=3.0, ceiling=1.0,
                air=False,pair_separation=None,embedded=False):
    # All dimensions here are mm. For a square finite-volume mesh, the
    # potential-flux sum already yields capacitance per metre.
    nx, ny = round(span/dx), round(ceiling/dx)
    x = (np.arange(nx)+.5)*dx-span/2
    y = (np.arange(ny)+.5)*dx
    xx, yy = np.meshgrid(x,y)
    copper_row=(yy>=height)&(yy<height+copper)
    strip = (abs(xx)<width/2) & copper_row
    negative=np.zeros_like(strip)
    ground_edge=width/2+gap
    if pair_separation is not None:
        strip=(abs(xx+pair_separation/2)<width/2)&copper_row
        negative=(abs(xx-pair_separation/2)<width/2)&copper_row
        ground_edge=pair_separation/2+width/2+gap
    coplanar = (abs(xx)>=ground_edge) & copper_row
    fixed = strip | negative | coplanar
    fixed[[0,-1],:] = True
    fixed[:,[0,-1]] = True
    value = np.zeros((ny,nx)); value[strip] = 1.0
    if pair_separation is not None:
        value[strip]=.5;value[negative]=-.5
    eps = np.where(yy<height,er,1.0)
    if embedded:eps[:]=er
    if mask:
        flat = (yy>=height)&(yy<height+mask)
        centers=[0] if pair_separation is None else [-pair_separation/2,pair_separation/2]
        near_roof=abs(xx)>=ground_edge-mask
        sides=abs(abs(xx)-ground_edge)<mask
        for center in centers:
            near_roof|=abs(xx-center)<width/2+mask
            sides|=abs(abs(xx-center)-width/2)<mask
        roof = (yy>=height+copper)&(yy<height+copper+mask)&near_roof
        sides &= (yy>=height)&(yy<height+copper)
        eps[flat|roof|sides] = mask_er
    if air: eps[:]=1.0
    unknown=~fixed
    ids=np.full((ny,nx),-1,dtype=np.int64)
    ids[unknown]=np.arange(unknown.sum())
    diagonal=np.zeros(unknown.sum()); rhs=np.zeros(unknown.sum())
    rows=[]; columns=[]; data=[]
    conductors=strip|negative|coplanar
    faces=[]
    for dy,ddx in [(1,0),(-1,0),(0,1),(0,-1)]:
        a=(slice(max(0,-dy),min(ny,ny-dy)),slice(max(0,-ddx),min(nx,nx-ddx)))
        z=(slice(max(0,dy),min(ny,ny+dy)),slice(max(0,ddx),min(nx,nx+ddx)))
        ea,ez=eps[a],eps[z]
        k=2*ea*ez/(ea+ez)
        # A metal face samples permittivity from its adjacent fluid cell.
        k=np.where(conductors[a],ez,k)
        k=np.where(conductors[z],ea,k)
        au=unknown[a]; zu=unknown[z]
        ia=ids[a][au]
        diagonal[ia]+=k[au]
        active=au&zu
        rows.append(ids[a][active]);columns.append(ids[z][active]);data.append(-k[active])
        grounded=au&fixed[z]
        rhs[ids[a][grounded]]+=k[grounded]*value[z][grounded]
        faces.append((a,z,k))
    rows.append(np.arange(unknown.sum()));columns.append(rows[-1]);data.append(diagonal)
    matrix=coo_matrix((np.concatenate(data),(np.concatenate(rows),np.concatenate(columns))),
                      shape=(unknown.sum(),unknown.sum())).tocsr()
    value[unknown]=spsolve(matrix,rhs)
    flux=0.0
    for a,z,k in faces:
        selected=strip[a]&~strip[z]
        flux+=np.sum(k[selected]*(value[a][selected]-value[z][selected]))
    return float(EPS0*flux),float(np.max(abs(matrix@value[unknown]-rhs))),int(unknown.sum())

def case(**kwargs):
    dielectric,residual,n=capacitance(**kwargs)
    vacuum,air_residual,_=capacitance(**kwargs,air=True)
    return dict(**kwargs,capacitance_pF_per_m=dielectric*1e12,
                air_capacitance_pF_per_m=vacuum*1e12,
                effective_permittivity=dielectric/vacuum,
                impedance_ohm=1/(C*np.sqrt(dielectric*vacuum)),
                max_discrete_residual=max(residual,air_residual),unknown_cells=n)

if __name__=='__main__':
    started=time.time()
    cases=[]
    for w in [.24,.26,.28,.30,.32]:
        r=case(width=w);cases.append(r);print(round(w,3),round(r['impedance_ohm'],3),flush=True)
    result=dict(method='2D finite-volume electrostatics / air-reference quasi-TEM estimate',
                scope='Nominal RF grounded coplanar uniform cross-section only',
                assumptions={'prepreg_mm':.18,'FR4_er':4.2,'copper_mm':.035,
                             'coplanar_ground_gap_mm':.2,'mask_mm':.01,'mask_er':3.5},
                cases=cases,elapsed_seconds=time.time()-started,
                manufacturer_stackup_confirmed=False,measured_impedance=False,
                antenna_matching_verified=False,whole_product_pass=False)
    directory=ROOT/'exports';directory.mkdir(exist_ok=True)
    (directory/'rf-field-estimate.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
