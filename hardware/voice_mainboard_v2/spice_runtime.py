"""Small ngspice shared-library runner. Outputs actual simulator vectors."""
from pathlib import Path
import ctypes as c
import os, re

ROOT=Path(__file__).resolve().parent
BIN=(ROOT.parents[1]/'build/cad-tools/kicad/bin').resolve()
os.add_dll_directory(str(BIN))
spice=c.CDLL(str(BIN/'ngspice.dll'))
LOG=c.CFUNCTYPE(c.c_int,c.c_char_p,c.c_int,c.c_void_p)
messages=[]
@LOG
def log(msg,i,u):
    text=msg.decode(errors='replace')
    messages.append(text)
    return 0
spice.ngSpice_Init.argtypes=[LOG,c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p]
assert spice.ngSpice_Init(log,None,None,None,None,None,None)==0
spice.ngSpice_Circ.argtypes=[c.POINTER(c.c_char_p)]
spice.ngSpice_Command.argtypes=[c.c_char_p]
for model in (BIN.parent/'lib/ngspice').glob('*.cm'):
    spice.ngSpice_Command(f'codemodel {model.as_posix()}'.encode())
spice.ngSpice_Command(b'set ngbehavior=ps')
class Vector(c.Structure):
    _fields_=[('name',c.c_char_p),('type',c.c_int),('flags',c.c_short),('real',c.POINTER(c.c_double)),('complex',c.c_void_p),('length',c.c_int)]
spice.ngGet_Vec_Info.argtypes=[c.c_char_p]
spice.ngGet_Vec_Info.restype=c.POINTER(Vector)
def run(name,lines,signals,out=None):
    messages.clear()
    spice.ngSpice_Command(b'destroy all')
    circuit=[name,*lines,'.end']
    if out:
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        (out/f'{name}.cir').write_text('\n'.join(circuit)+'\n',encoding='utf-8')
    raw=[x.encode() for x in circuit]+[None]
    if spice.ngSpice_Circ((c.c_char_p*len(raw))(*raw))!=0:raise RuntimeError('Circuit load: '+'; '.join(messages)[-4000:])
    if spice.ngSpice_Command(b'run')!=0:raise RuntimeError('Transient run: '+'; '.join(messages)[-4000:])
    result={}
    for sig in ['time',*signals]:
        p=spice.ngGet_Vec_Info(sig.encode())
        if not p:raise RuntimeError('Missing vector '+sig+': '+'; '.join(messages)[-4000:])
        v=p.contents;result[sig]=[v.real[i] for i in range(v.length)]
    if not result['time']:raise RuntimeError('Simulator returned no points')
    if out:
        (out/f'{name}.log').write_text('\n'.join(messages)+'\n',encoding='utf-8')
    # ngspice may return success even when a transient aborts at a short timestep.
    def number(text):
        m=re.fullmatch(r'([0-9.eE+\-]+)([a-zA-Z]*)',text)
        if not m:raise ValueError('Unsupported SPICE time '+text)
        return float(m[1])*{'':1,'s':1,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12,'f':1e-15}[m[2].lower()]
    transient=next((line.split() for line in lines if line.lower().startswith('.tran ')),None)
    if transient:
        end=number(transient[2])
        if result['time'][-1]<end*(1-1e-6):
            diagnostics=[m for m in messages if m.startswith('stderr')]
            raise RuntimeError(f'Transient stopped at {result["time"][-1]:.9g}s; expected {end:g}s. '+ '; '.join(diagnostics)[-1800:])
    return result,list(messages)
