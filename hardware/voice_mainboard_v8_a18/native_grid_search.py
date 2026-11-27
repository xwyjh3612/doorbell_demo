"""Optional .NET search using the exact same blocked grid and transition rules.

Emitted paths still go through exact geometry validation and native KiCad DRC.
No manufacturing rule or pad geometry is changed by this accelerator.
"""
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import numpy as np

def search(grids,via_grid,reuse_grid,rip_grids,sx,sy,gx,gy,source_layers,goal_nodes):
    nl=len(grids);ny,nx=grids[0].shape;plane=nx*ny
    root=Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='grid-',dir=root/'build/cad-tools') as folder:
        inp=Path(folder)/'input.bin';out=Path(folder)/'output.bin'
        with inp.open('wb') as f:
            f.write(struct.pack('<7i2d',nx,ny,nl,sx,sy,gx,gy,float(os.environ.get('A18_ROUTE_VIA_COST','18')),float(os.environ.get('A18_RIPUP_CROSSING_COST','10'))))
            f.write(struct.pack('<i',len(source_layers)))
            for li in source_layers:f.write(struct.pack('<i',li))
            f.write(struct.pack('<i',len(goal_nodes)))
            for x,y,li in goal_nodes:f.write(struct.pack('<i',li*plane+y*nx+x))
            f.write(np.stack(grids).astype(np.uint8).tobytes())
            f.write(via_grid.astype(np.uint8).tobytes());f.write(reuse_grid.astype(np.uint8).tobytes())
            f.write((np.stack(rip_grids) if rip_grids is not None else np.zeros((nl,ny,nx),dtype=np.uint8)).astype(np.uint8).tobytes())
        subprocess.run([str(root/'build/cad-tools/route-grid-search.exe'),str(inp),str(out)],check=True,capture_output=True,timeout=60)
        data=out.read_bytes();visited,count=struct.unpack_from('<2i',data)
        ids=np.frombuffer(data,dtype='<i4',count=count,offset=8)
        nodes=[(int(q%plane%nx),int(q%plane//nx),int(q//plane)) for q in ids]
        reachable=np.frombuffer(data,dtype=np.uint8,offset=8+count*4).reshape((nl,ny,nx)).astype(bool)
        return nodes,visited,reachable
