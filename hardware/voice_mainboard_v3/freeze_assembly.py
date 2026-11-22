"""Freeze purchasable assembly identities without changing any electrical net.

Small resistor families are specified by MPN but require stock confirmation.
No price allowance is a supplier quotation. PCB module land signoff remains
separate from matching the schematic/PCB/BOM identities.
"""
from pathlib import Path
import json,re
import pcbnew as p
root=Path(__file__).resolve().parent
d=json.loads((root/'design.json').read_text(encoding='utf8'))
b=p.LoadBoard(str(root/'voice_mainboard_v3.kicad_pcb'))
fps={f.GetReference():f for f in b.GetFootprints()}
known={
 'J1':('HX DC005-2.5-T','C18357600'),
 'J2':('DG350-3.5-02P-14-00A(H)','C2760668'),
 'J10':('SF72S006VBD','C2977286'),
 'J11':('U.FL-R-SMT-1(80)','C88374'),
 'U1':('ML307R-DL','C48982537'),
 'U2':('TPS62933PDRLR','C5219254'),
 'U6':('TPS63061DSCR','C2876326'),
 'U7':('TPD2E2U06DCKR-TP','C5350871'),
 'U8':('TP4056','C382139'),
 'U9':('TPS61230ARNSR','C376005'),
 'U10':('TPS2117DRLR','C22399676'),
 'U11':('LM393LVDGKR','C3659248'),
 'U12':('TLV431BIDBZR','C398375'),
 'D5':('BAT54C,215','C37704'),
 'Q3':('BSS84,215','C493579'),
}
for r in ['U3','U4','U5']:known[r]=('SN74AXC1T45DBVR','C2677376')
for r in ['Q1','Q2','Q4','Q5','Q7']:known[r]=('2N7002K-7','C85047')
# Q3's PMOS identity is kept until its catalog/land is independently checked.
for r in ['D1','D2','D3','D4']:known[r]=('PESD5V0U1BA,115','C552574')
caps={
 '100n':('CL10B104KB8NNNC','C1591'),
 '10n':('CL10B103KB8NNNC','C1589'),
 '33p':('CL10C330JB8NNNC','C1663'),
 '1n':('CL10C102JB8NNNC','C163508'),
 '1u':('CL10A105KB8NNNC','C15849'),
 '10u':('CL21A106KAYNNNE','C15850'),
}
header={2:('PZ254V-11-02P','C492401'),3:('PZ254V-11-03P','C2937625'),
        4:('PZ254V-11-04P','C2691448'),5:('PZ254V-11-05P','C492404'),
        30:('PZ254V-12-30P','C22465939')}
for item in d['parts']:
    ref=item['ref'];value=item['value']
    if ref in known:
        mpn,lcsc=known[ref];item.update(mpn=mpn,lcsc=lcsc)
        # Preserve service connector meanings instead of replacing them by MPN.
        if ref.startswith(('U','D','Q')):item['value']=mpn+' '+lcsc
    elif ref.startswith('C'):
        nominal=value.split()[0]
        if nominal in caps:
            mpn,lcsc=caps[nominal];item.update(mpn=mpn,lcsc=lcsc)
            item['value']=mpn+((' '+lcsc)if lcsc else '')
            item['electrical_value']=value
    elif ref.startswith('R'):
        nominal=value.split()[0].replace('R','')
        if nominal=='0':
            mpn=('RC0402JR070RL'if '0402' in item['footprint']else 'RC0603JR070RL')
        else:
            code=nominal.upper()
            if code.endswith(('K','M')):code+='L'
            elif '.' in code:
                code=code.replace('.', 'R')+'L'
            else:code+='RL'
            # EIA terminal code: 37.4k -> 37K4; 2.4M -> 2M4.
            m=re.fullmatch(r'(\d+)\.(\d+)([KM])L',code)
            if m:code=m[1]+m[3]+m[2]+'L'
            mpn=('RT0603BRD07'if '0.1%'in value else 'RC0603FR07')+code
        item['mpn']=mpn;item['procurement_status']='exact_mpn_stock_and_datasheet_pending'
    if 'Connector_PinHeader_'in item['footprint']:
        mpn,lcsc=header[len(item['pins'])];item.update(mpn=mpn,lcsc=lcsc)
    if 'mpn'in item and not item.get('procurement_status'):
        item['procurement_status']='selected_catalog_part_land_review_required'
    fps[ref].SetValue(item['value'])
    fps[ref].SetDNP(item['dnp'])
    # CAD-authoritative placement, not an earlier generation snapshot.
    item.update(x=p.ToMM(fps[ref].GetPosition().x),y=p.ToMM(fps[ref].GetPosition().y),
                angle=fps[ref].GetOrientationDegrees(),side='B'if fps[ref].IsFlipped()else 'F')
d['status']='CONNECTED V3 ENGINEERING DESIGN / PROCUREMENT AND POWER QUALIFICATION OPEN'
d['usb_transport_reserve']['host_connector']='J22 GND/DP20/DM19; J13 pin28 charge-disable GPIO38, pin29 NC'
d['ups_controls']['exact_inductor_capacitor_selection_complete']=True
d['assembly_contract']={
 'default_transport':'UART AT; R26/R27/R30 installed, R28/R29/R31/J22 DNP',
 'external_modules':['ESP32-S3 existing complete development board','INMP441 complete module','MAX98357 complete module'],
 'power_links':['JP4 2-3','JP1 1-2','J19 1-2','JP3 1-2'],
 'power_shunt_part_and_contact_resistance_verified':False,
 'usb_esd':'TECH PUBLIC C5350871: pins1/2 IO,3 GND; SOT323; manufacturer max0.7pF. Hardware IEC test pending.',
 'sim_esd':'Nexperia PESD5V0U1BA,115 C552574: SOD323, bidirectional,3.5pFmax; manufacturer20230401. Not S1BL/U1BL SOD882.',
 'battery':'External protected1S4.2V pack>=5A with10k/B3950 NTC; board is not independent cell protection',
 'manufacturing_ready':False,
}
p.SaveBoard(str(root/'voice_mainboard_v3.kicad_pcb'),b)
(root/'design.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Froze assembly identities, electrical nets unchanged; qualifications remain explicit')
