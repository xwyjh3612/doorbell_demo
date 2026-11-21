"""Embedded KiCad electrical pin-map schematic; labels carry the actual nets."""
from pathlib import Path
import json, uuid, math
ROOT=Path(__file__).resolve().parent
PROJECT='voice_mainboard_v2'
Q=lambda s:json.dumps(str(s),ensure_ascii=False)
UID=lambda s:str(uuid.uuid5(uuid.NAMESPACE_URL,'voice-mainboard-v2/'+s))
data=json.loads((ROOT/'design.json').read_text(encoding='utf-8'))
parts={p['ref']:p for p in data['parts'] if p['kind']!='mechanical'}
groups=[
 ('01 UPS RESERVE / GATED BATTERY ADC',[]),
 ('02 5V TO 3.8V MODEM BUCK',[]),
 ('03 ML307R-DL / 1.8V UART',[]),
 ('04 POWERKEY / RESET / DEBUG',[]),
 ('05 SIM / RF / USB SERVICE',[]),
 ('06 ESP / AUDIO / BUTTON / RADAR',[])]
for ref,p in parts.items():
    g=p['group'][:2]
    i={'01':0,'02':1,'03':2,'04':4,'05':5}[g]
    if g=='03' and ref not in ['U1','U3','U4','U5','R4','R5',*[f'C{k}' for k in range(13,19)]]:i=3
    if ref in ['Q3','Q4','Q5',*[f'R{k}' for k in range(15,25)],'C28','C29']:i=0
    groups[i][1].append(ref)
rootuid=UID('root')
header=f'''(kicad_sch (version 20250114) (generator "voice_mainboard_generator")
 (uuid {rootuid}) (paper "A0")
 (title_block (title "VOICE INTERCOM - ML307R-DL SMT / UPS RESERVED") (date "2026-11-21")
 (rev "V2-UNROUTED") (company "Engineering review / not for manufacture")
 (comment 1 "Net-labelled electrical pin map; UPS chip not selected")
 (comment 2 "109-pad land pattern transcribed from manufacturer; release signoff pending"))
'''
lib,placed,links=[],[],[]
def text(s,x,y,size=2):links.append(f'(text {Q(s)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid {UID("text/"+s)}))')
for gi,(title,refs) in enumerate(groups):
    xb=round((25+gi*191)/1.27)*1.27;text(title,xb,25,2)
    yc=40.64
    for ref in refs:
        p=parts[ref];names=p['names']
        pins=[(n,names.get(n,[n,'passive'])) for n in p['pins']]
        n=len(pins);split=math.ceil(n/2) if ref.startswith(('U','Q')) else n
        rows=max(split,n-split);h=max(7.62,(rows+1)*2.54)
        left,right=-20.32,20.32;xc=xb+86.36;ym=yc+h/2;libname='VoiceV2:'+ref
        s=[f'(symbol {Q(libname)} (pin_names (offset 0.5)) (in_bom yes) (on_board yes)',
          f'(property "Reference" {Q(ref)} (at 0 {h/2+2.54} 0) (effects (font (size 1.27 1.27))))',
          f'(property "Value" {Q(p["value"])} (at 0 {-h/2-2.54} 0) (effects (font (size 1.27 1.27))))',
          f'(property "Footprint" {Q(p["footprint"])} (at 0 0 0) (effects (font (size 1 1)) hide))',
          f'(symbol {Q(ref+"_0_1")} (rectangle (start {left} {h/2}) (end {right} {-h/2}) (stroke (width 0.254) (type default)) (fill (type background))))',
          f'(symbol {Q(ref+"_1_1")}']
        poses=[]
        for i,(num,(name,typ)) in enumerate(pins):
            side=int(i>=split);row=i if not side else i-split
            px=left-5.08 if not side else right+5.08;py=h/2-2.54*(row+1);ang=0 if not side else 180
            s.append(f'(pin {typ} line (at {px} {py} {ang}) (length 5.08) (name {Q(name)} (effects (font (size .9 .9)))) (number {Q(num)} (effects (font (size .9 .9)))))')
            poses.append((num,px,py,side))
        s.append('))');lib.append('\n'.join(s))
        dnp='yes' if p['dnp'] else 'no'
        a=[f'(symbol (lib_id {Q(libname)}) (at {xc} {ym} 0) (unit 1) (in_bom yes) (on_board yes) (dnp {dnp}) (uuid {UID("symbol/"+ref)})',
          f'(property "Reference" {Q(ref)} (at {xc} {yc-2} 0) (effects (font (size 1.27 1.27))))',
          f'(property "Value" {Q(p["value"]+(" [DNP]" if p["dnp"] else ""))} (at {xc} {yc+h+2} 0) (effects (font (size 1.05 1.05))))',
          f'(property "Footprint" {Q(p["footprint"])} (at {xc} {ym} 0) (effects (font (size 1 1)) hide))']
        for num,px,py,side in poses:
            a.append(f'(pin {Q(num)} (uuid {UID("pin/"+ref+"/"+num)}))')
            gx,gy=round(xc+px,6),round(ym-py,6);name=p['pins'][num]
            if not name:links.append(f'(no_connect (at {gx} {gy}) (uuid {UID("nc/"+ref+"/"+num)}))')
            else:
                ex=round(gx+(-5.08 if not side else 5.08),6)
                links.append(f'(wire (pts (xy {gx} {gy}) (xy {ex} {gy})) (stroke (width 0) (type default)) (uuid {UID("wire/"+ref+"/"+num)}))')
                links.append(f'(label {Q(name)} (at {ex} {gy} {0 if not side else 180}) (effects (font (size .95 .95)) (justify {"left" if not side else "right"} bottom)) (uuid {UID("label/"+ref+"/"+num)}))')
        a.append(f'(instances (project {Q(PROJECT)} (path "/{rootuid}" (reference {Q(ref)}) (unit 1)))) )');placed.append('\n'.join(a))
        yc+=h+12.7
    assert yc<785,(title,yc)
text('UPS RESERVE: actual charging, cell protection, power path, NTC and current limits must be designed after chip selection.',25,792,1.7)
text('Battery ADC: GPIO2 ADC1_CH1, enable GPIO9; 150k/100k + 100nF; Vbat = 2.5 x calibrated ADC volts. Protected 1S 4.2V assumed.',25,801,1.7)
text('No firmware changes: optional radar RX GPIO6 / reserved TX GPIO8; button GPIO0; modem PWRKEY GPIO11 / RESET GPIO21 proposed only.',25,810,1.7)
lib.append('''(symbol "VoiceV2:PWR_FLAG" (power) (pin_names (offset 0)) (in_bom no) (on_board no)
 (property "Reference" "#FLG" (at 0 2 0) (effects (font (size 1 1)) hide))
 (property "Value" "PWR_FLAG" (at 0 3 0) (effects (font (size 1 1))))
 (symbol "PWR_FLAG_0_1" (polyline (pts (xy -1 1) (xy 0 2) (xy 1 1) (xy 0 0) (xy -1 1)) (stroke (width 0.254) (type default)) (fill (type none))))
 (symbol "PWR_FLAG_1_1" (pin power_out line (at 0 0 90) (length 0) (name "pwr" (effects (font (size 1 1)))) (number "1" (effects (font (size 1 1)))))))''')
# Explicit external/converted source assumptions. Flags are NOT voltage/current verification.
for i,name in enumerate(['VIN_EXT_5V','SYS_5V','ESP_3V3','GND','MODEM_3V8','USB_DETECT_5V']):
    x,y=round((700+i*68)/1.27)*1.27,770.89;ref=f'#FLG0{i+1:02d}'
    placed.append(f'''(symbol (lib_id "VoiceV2:PWR_FLAG") (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (dnp no) (uuid {UID(ref)})
     (property "Reference" "{ref}" (at {x} {y-2} 0) (effects (font (size 1 1)) hide))
     (property "Value" "PWR_FLAG" (at {x} {y-3} 0) (effects (font (size 1 1))))
     (pin "1" (uuid {UID('pin/'+ref)})) (instances (project "{PROJECT}" (path "/{rootuid}" (reference "{ref}") (unit 1)))))''')
    links.append(f'(label "{name}" (at {x} {y} 0) (effects (font (size 1 1)) (justify left bottom)) (uuid {UID("flag/"+name)}))')
(ROOT/(PROJECT+'.kicad_sch')).write_text(header+'(lib_symbols\n'+'\n'.join(lib)+')\n'+'\n'.join(placed+links)+'\n)',encoding='utf-8')
(ROOT/'VoiceV2.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "voice_mainboard_generator")\n'+'\n'.join(s.replace('(symbol "VoiceV2:', '(symbol "') for s in lib)+'\n)',encoding='utf-8')
(ROOT/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "VoiceV2") (type "KiCad") (uri "${KIPRJMOD}/VoiceV2.kicad_sym") (options "") (descr "V2 draft electrical pin-map symbols")))',encoding='utf-8')
(ROOT/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "VoiceV2") (type "KiCad") (uri "${KIPRJMOD}/VoiceV2.pretty") (options "") (descr "ML307R-DL manufacturer land-pattern transcription draft")))',encoding='utf-8')
(ROOT/'schematic-ids.json').write_text(json.dumps({'root':rootuid,'symbols':{ref:UID('symbol/'+ref) for ref in parts}},indent=2),encoding='utf-8')
print('Generated',len(parts),'electrical symbols, A0 review sheet')
