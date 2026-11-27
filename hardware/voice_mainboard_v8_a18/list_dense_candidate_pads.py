"""List real used dense pins for a routing candidate's initial escape pass."""
import collections,os
import pcbnew as p
b=p.LoadBoard(os.environ['A18_REPAIR_BOARD'])
fps={f.GetReference():f for f in b.GetFootprints()}
counts=collections.Counter(d.GetNetname()for f in b.GetFootprints()for d in f.Pads())
priority=[('U1','59'),('U1','60'),('U1','82')]
refs=['U1','U7','U14','U2','U13','U15','U3','U4','U5','U16','U17','R28','R29']
targets=[]
for ref,num in priority+[(ref,d.GetNumber())for ref in refs for d in fps[ref].Pads()]:
    d=next(d for d in fps[ref].Pads()if d.GetNumber()==num)
    net=d.GetNetname();value=f'{ref}.{num}'
    if net and net!='GND'and not net.startswith('unconnected-')and counts[net]>1 and value not in targets:targets.append(value)
print(','.join(targets))
