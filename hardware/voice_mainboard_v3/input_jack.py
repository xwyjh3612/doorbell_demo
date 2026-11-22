"""HX DC005-2.5-T footprint, transcribed from manufacturer TOP VIEW drawing.

Manufacturer pad numbers are retained: 4=center+, 2=sleeve, 3=switched sleeve.
Plated slots follow the recommended PCB layout. Verify an actual sample before
series assembly. This is not the footprint of an arbitrary DC005 connector.
"""
from pathlib import Path
import pcbnew as p
held=[]
def vec(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def replace(board,parts,root):
    fps=list(board.GetFootprints());tracks=list(board.GetTracks())
    old=next(f for f in fps if f.GetReference()=='J1')
    if old.GetFPID().GetLibItemName()=='HX_DC005_2p5_T':return 0
    held.extend([old,*tracks]);board.Remove(old)
    fp=p.FOOTPRINT(board);fp.SetFPID(p.LIB_ID('VoiceV2','HX_DC005_2p5_T'));fp.SetAttributes(p.FP_THROUGH_HOLE)
    for number,x,y,hole,size in [('4',13.8,0,(1,3),(1.8,3.8)),('3',7.5,0,(1,3),(1.8,3.8)),('2',10.8,4.6,(3,.8),(4,1.8))]:
        pad=p.PAD(fp);pad.SetNumber(number);pad.SetAttribute(p.PAD_ATTRIB_PTH);pad.SetShape(p.PAD_SHAPE_OVAL)
        pad.SetPosition(vec(x,y));pad.SetSize(vec(*size));pad.SetDrillSize(vec(*hole));pad.SetDrillShape(p.PAD_DRILL_SHAPE_OBLONG)
        layers=p.LSET.AllCuMask();layers.AddLayer(p.F_Mask);layers.AddLayer(p.B_Mask);pad.SetLayerSet(layers);fp.Add(pad)
    for layer,x1,y1,x2,y2,w in [(p.F_Fab,0,-5.5,14.2,5.5,.1),(p.F_CrtYd,-.25,-5.75,14.95,5.75,.05)]:
        for a,z in [((x1,y1),(x2,y1)),((x2,y1),(x2,y2)),((x2,y2),(x1,y2)),((x1,y2),(x1,y1))]:
            sh=p.PCB_SHAPE(fp);sh.SetShape(p.SHAPE_T_SEGMENT);sh.SetStart(vec(*a));sh.SetEnd(vec(*z));sh.SetLayer(layer);sh.SetWidth(p.FromMM(w));fp.Add(sh)
    fp.SetLibDescription('HX DC005-2.5-T C18357600; Hanxia Rev2020.8.11 TOP VIEW.14.20x9.00x11.00mm body,3A/30V,2.5mm center. Mfr4 center+,2 sleeve,3 switched.2x1.0x3.0 and1x3.0x0.8 plated slots.')
    plugin=p.PCB_IO_MGR.PluginFind(p.PCB_IO_MGR.KICAD_SEXP);plugin.FootprintSave(str(root/'VoiceV2.pretty'),fp)
    fp.SetReference('J1');fp.SetValue('HX DC005-2.5-T 3A C18357600');fp.SetPosition(vec(.5,13.5))
    fp.Reference().SetLayer(p.F_Fab);fp.Reference().SetTextSize(vec(.75,.75));fp.Reference().SetTextThickness(p.FromMM(.12));fp.Value().SetVisible(False)
    for pd in fp.Pads():
        name={'4':'VIN_DC','2':'GND'}.get(pd.GetNumber())
        if name:pd.SetNet(board.FindNet(name))
    board.Add(fp)
    count=0
    for t in tracks:
        if t.GetNetname()=='VIN_DC':board.Remove(t);count+=1
    item=next(x for x in parts if x['ref']=='J1')
    item.update(value=fp.GetValue(),footprint='VoiceV2:HX_DC005_2p5_T',x=.5,y=13.5,angle=0,side='F',
      pins={'4':'VIN_DC','2':'GND','3':''},names={'4':['CENTER_PLUS_MFR4','passive'],'2':['SLEEVE_MFR2','passive'],'3':['SW_UNUSED_MFR3','passive']},
      source='https://item.szlcsc.com/19545770.html',
      note='Hanxia HX DC005-2.5-T,3.0A/30V rating,2.5mm checked manufacturer drawing2020.8.11,C18357600. Public0.3837CNY stock4187 on20261122. PCB top-view slots transcribed, needs physical sample fit. Center+ is manufacturer pad4, not1; pin3 unused.')
    return count
if __name__=='__main__':
    import json
    root=Path(__file__).resolve().parent;b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
    d=json.loads((root/'design.json').read_text(encoding='utf8'));removed=replace(b,d['parts'],root)
    assert p.ZONE_FILLER(b).Fill(b.Zones());p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
    d['input_power']['jack_part']='HX DC005-2.5-T C18357600,3A socket/2A system target'
    (root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Qualified-current input jack placed; old VIN_DC tracks removed:',removed)
