"""Create an embedded-symbol, net-labelled KiCad review schematic from design.json.

Requires only Python 3. The PCB uses the same reference/pin/net table; the netlist
export is checked independently by KiCad, rather than assuming the drawing loads.
"""
from pathlib import Path
import json, uuid, math

ROOT = Path(__file__).resolve().parent
PROJECT = 'voice_carrier_v1'
UID = lambda value: str(uuid.uuid5(uuid.NAMESPACE_URL, 'voice-carrier-v1/' + value))
Q = lambda text: json.dumps(str(text), ensure_ascii=False)
data = json.loads((ROOT / 'design.json').read_text(encoding='utf-8'))
parts = {p['ref']: p for p in data['parts'] if p['kind'] != 'mechanical'}

# Exact IC pin meanings/types, checked against the manufacturer's pin tables.
ic = {
 'U1': [('TEMP','input'),('PROG','passive'),('GND','power_in'),('VCC','power_in'),('BAT_CHARGE','passive'),('STDBY','open_collector'),('CHRG','open_collector'),('CE','input'),('EP','power_in')],
 'U2': [('CBST','passive'),('EN','input'),('FB','input'),('VIN','power_in'),('SW','passive'),('GND','power_in'),('VOUT','power_out')],
 'U3': [('GND','power_in'),('VOUT','power_out'),('VIN1','power_in'),('PR1','input'),('MODE','input'),('VIN2','power_in'),('VOUT','passive'),('ST','open_collector')],
 'U4': [('GND','power_in'),('RESET_N','open_collector'),('VDD','power_in')],
 'U5': [('OUT1','open_collector'),('IN1_N','input'),('IN1_P','input'),('GND','power_in'),('IN2_P','input'),('IN2_N','input'),('OUT2','open_collector'),('VCC','power_in')],
 'U6': [('K','passive'),('REF','passive'),('A','passive')],
 'D1': [('A1','passive'),('A2','passive'),('K_COMMON','passive')]
}
groups = [
 ('01  INPUT / CHARGE / BATTERY TEMPERATURE', ['J1','J2','J4','U1','R1','R2','R3','C1','C2','C12']),
 ('02  BATTERY BOOST / HARDWARE UNDERVOLTAGE', ['U2','L1','C3','C4','C5','C6','R4','R5','U4','R6','C10']),
 ('03  AUTOMATIC SOURCE SELECTION', ['U3','C7','C8','C9','D1','U5','U6','R7','R8','R9','R10','R11','C11']),
 ('04  MEASUREMENT / BUTTON / RADAR POWER', ['R12','R13','C13','R14','R15','C14','R16','R17','R18','R19','C15','C16']),
 ('05  EXISTING MODULE HARNESS INTERFACES', ['J3','J5','J6','J7','J8','J9','J10','JP1','JP2','TP1','TP2']),
]
assert set(sum([refs for _,refs in groups], [])) == set(parts)
rootuid = UID('root')
header = f'''(kicad_sch (version 20250114) (generator "voice_carrier_generator")
  (uuid {rootuid}) (paper "A1")
  (title_block (title "VOICE INTERCOM - V1 ENGINEERING DRAFT") (date "2026-11-19")
   (rev "V1-DRAFT") (company "Existing module carrier / optional radar")
   (comment 1 "Net-labelled review drawing; not released for manufacturing")
   (comment 2 "Connector pin numbers refer to this carrier, not module headers"))
'''
lib, placed, links = [], [], []

def text(txt,x,y,size=2.0):
    links.append(f'(text {Q(txt)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid {UID("text/"+txt)}))')

for gi,(title,refs) in enumerate(groups):
    xbase = round((30 + gi*158)/1.27)*1.27
    text(title,xbase,28,2)
    ycur = 44.45
    for ref in refs:
        p = parts[ref]
        pins = [(n, ic[ref][int(n)-1] if ref in ic else (n,'passive')) for n in p['pins']]
        n = len(pins)
        # ICs on two sides; connectors on one side for easy pin-map reading.
        split = math.ceil(n/2) if ref.startswith('U') or ref=='D1' else n
        rows = max(split,n-split)
        h = max(7.62,(rows+1)*2.54)
        left, right = -12.7,12.7
        ymid = ycur + h/2
        libname = 'Voice:' + ref
        sym = [f'(symbol {Q(libname)} (pin_names (offset 0.5)) (in_bom yes) (on_board yes)',
          f'(property "Reference" {Q(ref)} (at 0 {h/2+2.54} 0) (effects (font (size 1.27 1.27))))',
          f'(property "Value" {Q(p["value"])} (at 0 {-h/2-2.54} 0) (effects (font (size 1.27 1.27))))',
          f'(property "Footprint" {Q(p["footprint"])} (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
          f'(symbol {Q(ref+"_0_1")} (rectangle (start {left} {h/2}) (end {right} {-h/2}) (stroke (width 0.254) (type default)) (fill (type background))))',
          f'(symbol {Q(ref+"_1_1")}']
        pinpos = []
        for i,(num,(name,typ)) in enumerate(pins):
            side = 0 if i<split else 1
            row = i if side==0 else i-split
            px = left-5.08 if side==0 else right+5.08
            py = h/2-2.54*(row+1)
            angle = 0 if side==0 else 180
            sym.append(f'(pin {typ} line (at {px} {py} {angle}) (length 5.08) (name {Q(name)} (effects (font (size 1.0 1.0)))) (number {Q(num)} (effects (font (size 1.0 1.0)))))')
            pinpos.append((num,px,py,side))
        sym.append('))');lib.append('\n'.join(sym))
        instuid = UID('symbol/'+ref)
        xc=xbase+62.23
        attrs=[f'(symbol (lib_id {Q(libname)}) (at {xc} {ymid} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {instuid})',
           f'(property "Reference" {Q(ref)} (at {xc} {ycur-2} 0) (effects (font (size 1.27 1.27))))',
           f'(property "Value" {Q(p["value"])} (at {xc} {ycur+h+2} 0) (effects (font (size 1.27 1.27))))',
           f'(property "Footprint" {Q(p["footprint"])} (at {xc} {ymid} 0) (effects (font (size 1.27 1.27)) hide))']
        for num,px,py,side in pinpos:
            attrs.append(f'(pin {Q(num)} (uuid {UID("pin/"+ref+"/"+num)}))')
            gx,gy=round(xc+px,6),round(ymid-py,6)
            name=p['pins'][num]
            if not name:
                links.append(f'(no_connect (at {gx} {gy}) (uuid {UID("nc/"+ref+"/"+num)}))')
            else:
                ex=round(gx+(-5.08 if side==0 else 5.08),6)
                links.append(f'(wire (pts (xy {gx} {gy}) (xy {ex} {gy})) (stroke (width 0) (type default)) (uuid {UID("wire/"+ref+"/"+num)}))')
                links.append(f'(label {Q(name)} (at {ex} {gy} {0 if side==0 else 180}) (effects (font (size 1.0 1.0)) (justify {"left" if side==0 else "right"} bottom)) (uuid {UID("label/"+ref+"/"+num)}))')
        attrs.append(f'(instances (project {Q(PROJECT)} (path "/{rootuid}" (reference {Q(ref)}) (unit 1)))) )')
        placed.append('\n'.join(attrs))
        ycur += h+15.24
    assert ycur < 545, (title,ycur)

# Harness-supplied rails and diode-OR control rail require electrical source flags.
# These flags only model the supply sources in ERC, not protection circuits.
lib.append('''(symbol "Voice:PWR_FLAG" (power) (pin_names (offset 0)) (in_bom no) (on_board no)
 (property "Reference" "#FLG" (at 0 2 0) (effects (font (size 1.27 1.27)) hide))
 (property "Value" "PWR_FLAG" (at 0 3 0) (effects (font (size 1.27 1.27))))
 (symbol "PWR_FLAG_0_1" (polyline (pts (xy -1 1) (xy 0 2) (xy 1 1) (xy 0 0) (xy -1 1)) (stroke (width 0.254) (type default)) (fill (type none))))
 (symbol "PWR_FLAG_1_1" (pin power_out line (at 0 0 90) (length 0) (name "pwr" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))))''')
for i,name in enumerate(['VIN_EXT','VBAT','V3V3','GND','VCTL']):
    x,y=round((40+i*42)/1.27)*1.27,557.53
    ref=f'#FLG0{i+1:02d}'
    placed.append(f'''(symbol (lib_id "Voice:PWR_FLAG") (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (dnp no) (uuid {UID(ref)})
    (property "Reference" "{ref}" (at {x} {y-2} 0) (effects (font (size 1 1)) hide))
    (property "Value" "PWR_FLAG" (at {x} {y-3} 0) (effects (font (size 1 1))))
    (pin "1" (uuid {UID('pin/'+ref)}))
    (instances (project "{PROJECT}" (path "/{rootuid}" (reference "{ref}") (unit 1)))))''')
    links.append(f'(label "{name}" (at {x} {y} 0) (effects (font (size 1 1)) (justify left bottom)) (uuid {UID("flag-label/"+name)}))')
text('POWER FLAGS: external/battery/ESP32 3V3 supplies and diode-OR VCTL. Protected 1S pack required.',30,568,1.6)
text('Radar is optional: J9 pin 3 = module TX -> ESP32 GPIO6. Pin 4 = module RX <- reserved GPIO8.',260,558,1.6)
text('Button and battery monitoring need firmware adaptation; ADC GPIO assignment and module mechanical fit remain open.',260,567,1.6)
(ROOT/(PROJECT+'.kicad_sch')).write_text(header+'(lib_symbols\n'+'\n'.join(lib)+')\n'+'\n'.join(placed+links)+'\n)',encoding='utf-8')
(ROOT/'Voice.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "voice_carrier_generator")\n'+ '\n'.join(s.replace('(symbol "Voice:', '(symbol "') for s in lib)+'\n)',encoding='utf-8')
(ROOT/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "Voice") (type "KiCad") (uri "${KIPRJMOD}/Voice.kicad_sym") (options "") (descr "V1 draft embedded pin-map symbols")))',encoding='utf-8')
(ROOT/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "Voice") (type "KiCad") (uri "${KIPRJMOD}/Voice.pretty") (options "") (descr "TI asymmetric package draft footprints")))',encoding='utf-8')
(ROOT/'schematic-ids.json').write_text(json.dumps({'root':rootuid,'symbols':{ref:UID('symbol/'+ref) for ref in parts}},indent=2),encoding='utf-8')
print('Created embedded schematic:',len(parts),'electrical components')
