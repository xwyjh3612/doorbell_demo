"""Generate a local, layered copper inspection SVG (not a fabrication plot)."""
import sys
from pathlib import Path
import pcbnew as p
root=Path(__file__).resolve().parent
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
x,y,w,h=map(float,sys.argv[1:5]) if len(sys.argv)>4 else (12,44,14,10)
out=['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1000" viewBox="%s %s %s %s">'%(x,y,w,h),'<rect x="%s" y="%s" width="%s" height="%s" fill="white"/>'%(x,y,w,h)]
colors={p.F_Cu:'#e04040',p.B_Cu:'#4090e0',p.In2_Cu:'#aa6ad0'}
for t in b.GetTracks():
    if isinstance(t,p.PCB_VIA):
        xx,yy=p.ToMM(t.GetPosition().x),p.ToMM(t.GetPosition().y)
        out.append('<circle cx="%s" cy="%s" r="%s" fill="#bbb" stroke="#222" stroke-width=".03"/>'%(xx,yy,p.ToMM(t.GetWidth(p.F_Cu))/2))
        out.append('<circle cx="%s" cy="%s" r="%s" fill="white"/>'%(xx,yy,p.ToMM(t.GetDrill())/2))
    elif t.GetLayer() in colors:
        a,z=t.GetStart(),t.GetEnd()
        out.append('<path d="M%s %s L%s %s" stroke="%s" stroke-width="%s" stroke-linecap="round" opacity=".65"/>'%(p.ToMM(a.x),p.ToMM(a.y),p.ToMM(z.x),p.ToMM(z.y),colors[t.GetLayer()],p.ToMM(t.GetWidth())))
for f in b.GetFootprints():
    for pd in f.Pads():
        color=colors[p.F_Cu if pd.IsOnLayer(p.F_Cu) else p.B_Cu]
        layer=p.F_Cu if pd.IsOnLayer(p.F_Cu) else p.B_Cu
        poly=pd.GetEffectivePolygon(layer)
        for k in range(poly.OutlineCount()):
            ch=poly.COutline(k)
            pts=' '.join('%s,%s'%(p.ToMM(ch.CPoint(i).x),p.ToMM(ch.CPoint(i).y))for i in range(ch.PointCount()))
            out.append('<polygon points="%s" fill="%s" stroke="#222" stroke-width=".025"/>'%(pts,color))
    xx,yy=p.ToMM(f.GetPosition().x),p.ToMM(f.GetPosition().y)
    out.append('<text x="%s" y="%s" font-size=".28" fill="#111">%s</text>'%(xx,yy,f.GetReference()))
out.append('</svg>')
(root/'exports/copper-inspection.svg').write_text('\n'.join(out),encoding='utf8')
