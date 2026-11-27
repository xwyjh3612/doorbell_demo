"""Export current CAD layers to SVG/PNG for a reproducible local review."""
from pathlib import Path
import ctypes, ctypes.util, os, subprocess
SOURCE=Path(__file__).resolve().parent;REPO=SOURCE.parents[1]
FILE=Path(os.environ.get('A18_AUDIT_BOARD',str(SOURCE/'voice_mainboard_v8_a18.kicad_pcb'))).resolve()
OUT=FILE.parent/'exports';OUT.mkdir(exist_ok=True)
cli=REPO/'build/cad-tools/kicad/bin/kicad-cli.exe'
for side in ['front','back']:
    layer='F'if side=='front'else'B'
    args=[str(cli),'pcb','export','svg','--layers',f'{layer}.Cu,{layer}.Fab,Edge.Cuts','--mode-single','--exclude-drawing-sheet','--page-size-mode','2','--output',str(OUT/f'review-{side}.svg')]
    if side=='back':args.append('--mirror')
    subprocess.run([*args,str(FILE)],check=True,capture_output=True)
cairo=str(REPO/'build/cad-tools/kicad/bin/cairo-2.dll')
ctypes.CDLL(cairo);old_find=ctypes.util.find_library
ctypes.util.find_library=lambda name:cairo if name=='cairo'else old_find(name)
import cairosvg
for side in ['front','back']:
    cairosvg.svg2png(url=str(OUT/f'review-{side}.svg'),write_to=str(OUT/f'review-{side}.png'),output_width=1500,background_color='#121a1f')
print('Rendered current CAD front/back images:',FILE.name)
