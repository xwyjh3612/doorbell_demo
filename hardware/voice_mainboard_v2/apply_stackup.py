"""Record the requested four-layer stack in the KiCad fabrication data.

This is a fabrication requirement, not a claim that a manufacturer has already
measured these materials. Factory impedance coupons remain necessary.
"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parent
path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'voice_mainboard_v2.kicad_pcb'
text=path.read_text(encoding='utf8')
start=text.find('(stackup')
if start>=0:
    depth=0;quoted=False;escaped=False
    for end in range(start,len(text)):
        ch=text[end]
        if escaped:escaped=False;continue
        if ch=='\\' and quoted:escaped=True;continue
        if ch=='"':quoted=not quoted
        if quoted:continue
        if ch=='(':depth+=1
        elif ch==')':
            depth-=1
            if depth==0:break
    text=text[:start]+text[end+1:]
stack='''
        (stackup
            (layer "F.SilkS" (type "Top Silk Screen"))
            (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01)
                (material "Solder Mask") (epsilon_r 3.5) (loss_tangent 0.02))
            (layer "F.Cu" (type "copper") (thickness 0.035))
            (layer "dielectric 1" (type "prepreg") (thickness 0.18)
                (material "FR4") (epsilon_r 4.2) (loss_tangent 0.02))
            (layer "In1.Cu" (type "copper") (thickness 0.0175))
            (layer "dielectric 2" (type "core") (thickness 1.135)
                (material "FR4") (epsilon_r 4.2) (loss_tangent 0.02))
            (layer "In2.Cu" (type "copper") (thickness 0.0175))
            (layer "dielectric 3" (type "prepreg") (thickness 0.18)
                (material "FR4") (epsilon_r 4.2) (loss_tangent 0.02))
            (layer "B.Cu" (type "copper") (thickness 0.035))
            (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01)
                (material "Solder Mask") (epsilon_r 3.5) (loss_tangent 0.02))
            (layer "B.SilkS" (type "Bottom Silk Screen"))
            (copper_finish "HASL lead-free")
            (dielectric_constraints yes)
            (edge_connector no)
            (castellated_pads no)
            (edge_plating no)
        )'''
assert text.count('(setup')==1
text=text.replace('(setup','(setup'+stack,1)
path.write_text(text,encoding='utf8')
evidence=dict(total_copper_and_laminate_mm=1.6,finished_board_nominal_mm=1.6,
              finished_board_tolerance_percent=10,outer_copper_um=35,inner_copper_um=17.5,
              outer_prepreg_mm=.18,outer_prepreg_requirement_mm=[.17,.19],
              dielectric_er_nominal=4.2,dielectric_er_requirement=[4.0,4.4],
              reference_plane='In1.Cu continuous GND',
              rf_geometry={'width_mm':.28,'coplanar_gap_mm':.2,'target_ohm':50,'tolerance_percent':10},
              usb_host_pair={'layer':'F.Cu','width_mm':.28,'gap_mm':.22,'target_differential_ohm':90,
                             'measured':False,'reference_review_required':True},
              supplier_stackup_confirmed=False,impedance_coupons_measured=False)
(ROOT/'fabrication-stackup.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
print('Recorded required stack; factory material/coupon verification is pending.')
