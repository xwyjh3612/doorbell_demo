"""Export complete read-only signal reachability from one real pad.

An intentionally out-of-board goal forces search exhaustion, not new copper.
"""
import json
import os
from comparison_route_geometry import b,FILE,p,pos,layers,route

ref,number=os.environ['A18_FIELD_PAD'].split('.')
f=next(f for f in b.GetFootprints()if f.GetReference()==ref)
d=next(d for d in f.Pads()if d.GetNumber()==number)
net=d.GetNetname();dest=FILE.parent/'exports'/('field-'+net+'.npz')
os.environ['A18_ROUTE_DIAGNOSTIC_FILE']=str(dest)
try:
    route(net,pos(d),(74,74),{i for i,l in enumerate(layers)if d.IsOnLayer(l)},set(range(len(layers))),
        width=float(os.environ.get('A18_FIELD_WIDTH','.16')),step=.05)
except RuntimeError as error:print(net,ref,number,str(error),flush=True)
assert dest.exists()
