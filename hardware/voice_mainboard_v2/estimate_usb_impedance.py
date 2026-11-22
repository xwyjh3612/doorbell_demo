"""Estimate the routed Host pair's uniform cross-section with mesh checks."""
from pathlib import Path
import json,time
from field_impedance import case

ROOT=Path(__file__).resolve().parent
base=dict(width=.28,height=.18,gap=.2,copper=.035,er=4.2,
          mask=.01,mask_er=3.5,pair_separation=.5)
started=time.time();cases=[]
for label,changes in [('nominal',{}),('fine_grid',{'dx':.0025}),
                      ('larger_domain',{'span':4.0,'ceiling':1.2}),
                      ('thin_high_er',{'height':.17,'er':4.4}),
                      ('thick_low_er',{'height':.19,'er':4.0})]:
    result=case(**(base|changes));result['label']=label;cases.append(result)
    print(label,round(result['impedance_ohm'],3),flush=True)
result=dict(method='2D finite-volume electrostatics, +0.5/-0.5V differential pair',
            scope='Uniform F.Cu Host pair over In1 ground only; excludes headers, fanouts and cable',
            assumptions=base,target_differential_ohm=90,tolerance_percent=10,
            cases=cases,elapsed_seconds=time.time()-started,
            manufacturer_stackup_confirmed=False,measured_impedance=False,
            actual_usb_eye_test_passed=False,whole_product_pass=False)
(ROOT/'exports/usb-field-estimate.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
