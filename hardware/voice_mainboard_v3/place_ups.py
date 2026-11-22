"""Deterministic local placement with real KiCad package bounding boxes.

Power ICs stay on the front. Slow comparator/reference parts occupy the back
behind the charging area, with internal ground shielding from switch nodes.
This geometric packing is followed by KiCad DRC, not treated as approval.
"""
import math
import pcbnew as pcb

def place(board,parts):
    fps={f.GetReference():f for f in board.GetFootprints()}
    metadata={p['ref']:p for p in parts}
    moved={'J16':(34,61),'JP2':(46,61),'JP3':(37,65),'C26':(46.5,65),'TP9':(30,55)}
    for ref,(x,y)in moved.items():fps[ref].SetPosition(pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y)))
    back={'U11','U12','D5','Q7',*[f'R{k}'for k in range(42,55)],*[f'C{k}'for k in range(49,53)],'R22','R23','R24'}
    targets={'U11':(15,66),'U12':(8,50),'D5':(9,45.5),'R42':(4.5,47),'R43':(7,53),'R44':(7,56),'C49':(9,53),
      'C50':(14,45.5),'R45':(19,45.5),'R46':(19,48.5),'R47':(21,51),'R48':(19,54),'R49':(19,57),
      'C51':(16,57),'R50':(24,45.5),'R51':(24,48.5),'R52':(24,51),'R53':(24,54),'R54':(24,57),
      'C52':(26,60),'R22':(6,59),'R23':(10,59),'R24':(15,60),'L3':(11,57),'U8':(11,49),'U9':(18,57),
      'C40':(4,57),'C41':(15.5,60.5),'C42':(21,56),'C43':(24,56),'C44':(25,61.5),'C45':(21.5,59.5),
      'R40':(18.75,59.5),'R41':(21.75,59.5),'C53':(24,50),'J4':(11,70),'U10':(18,48),'Q7':(25,65)}
    for ref in back:
        f=fps[ref]
        if f.GetLayer()!=pcb.B_Cu:f.Flip(f.GetPosition(),True)
    front_new={r for r in fps if metadata[r]['group'].startswith(('07','08'))}-back
    fixed=set(fps)-front_new-back

    def bbox(f):
        b=f.GetBoundingBox(False,False)
        return tuple(pcb.ToMM(x)for x in (b.GetLeft(),b.GetTop(),b.GetRight(),b.GetBottom()))
    def overlap(a,b,gap=.04):
        return a[0]<b[2]+gap and a[2]>b[0]-gap and a[1]<b[3]+gap and a[3]>b[1]-gap
    def padbox(p):
        b=p.GetBoundingBox();return tuple(pcb.ToMM(x)for x in (b.GetLeft(),b.GetTop(),b.GetRight(),b.GetBottom()))
    through=[padbox(p)for f in fps.values()for p in f.Pads()if p.GetAttribute()==pcb.PAD_ATTRIB_PTH]
    # Pack large power bodies first; fit capacitors/resistors around the local
    # electrical anchors. Analog reference/IC is first on the opposite side.
    front_order=['J2','L3','U8','U9','U10','C48','C45','C41','R40','R41','C40','J4']
    front_order += sorted(front_new-set(front_order),key=lambda r:-(bbox(fps[r])[2]-bbox(fps[r])[0])*(bbox(fps[r])[3]-bbox(fps[r])[1]))
    back_order=['U11','U12','D5']+sorted(back-{'U11','U12','D5'})
    for order,side in [(front_order,pcb.F_Cu),(back_order,pcb.B_Cu)]:
        occupied=[bbox(fps[r])for r in fixed if fps[r].GetLayer()==side]
        if side==pcb.B_Cu:
            occupied += [padbox(p)for f in fps.values()for p in f.Pads()if p.GetAttribute()==pcb.PAD_ATTRIB_PTH]
        for ref in order:
            f=fps[ref];p=f.GetPosition();b=bbox(f)
            px,py=pcb.ToMM(p.x),pcb.ToMM(p.y)
            relative=(b[0]-px,b[1]-py,b[2]-px,b[3]-py)
            tx,ty=targets.get(ref,(px,py))
            candidates=[]
            for ix in range(17,117):
                x=ix*.25
                for iy in range(177,294):
                    y=iy*.25
                    box=(x+relative[0],y+relative[1],x+relative[2],y+relative[3])
                    if box[0]<2.5 or box[1]<43.75 or box[2]>29.25 or box[3]>73.5:continue
                    if any(overlap(box,o)for o in occupied):continue
                    candidates.append(((x-tx)**2+(y-ty)**2,x,y,box))
            if not candidates:raise RuntimeError('No local placement for '+ref+'; expand/revise layout, never hide overlap')
            _,x,y,box=min(candidates)
            f.SetPosition(pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y)));occupied.append(box)
    for ref,f in fps.items():
        p=f.GetPosition();metadata[ref].update(x=pcb.ToMM(p.x),y=pcb.ToMM(p.y),angle=f.GetOrientationDegrees(),side='B'if f.GetLayer()==pcb.B_Cu else'F')
    return {'front_power_refs':front_order,'back_analog_refs':back_order,'existing_moved':moved,'manufacturing_ready':False}
