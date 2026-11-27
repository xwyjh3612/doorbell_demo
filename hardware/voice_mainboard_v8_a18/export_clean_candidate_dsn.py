"""Export native pad geometry with explicit routing classes and no ground planes.

Ground pin ownership is retained. Skip only the GROUND class while routing;
the final native PCB must still connect every ground through real copper.
"""
from pathlib import Path
import hashlib,json,re,os
import pcbnew as p
from comparison_route_geometry import b,FILE

OUT=FILE.parent
assert p.ExportSpecctraDSN(b,str(OUT/'signals.dsn'))
text=(OUT/'signals.dsn').read_text(encoding='utf-8')
def span(source,start):
    opening=source.index('(',start);depth=0;quoted=False;escaped=False
    for i in range(opening,len(source)):
        ch=source[i]
        if quoted:
            if escaped:escaped=False
            elif ch=='\\':escaped=True
            elif ch=='"':quoted=False
            continue
        if ch=='"':quoted=True
        elif ch=='(':depth+=1
        elif ch==')':
            depth-=1
            if depth==0:return opening,i+1
    raise RuntimeError('Unbalanced DSN')
while '    (plane GND 'in text:
    start=text.index('    (plane GND ');a,z=span(text,start);text=text[:start]+text[z:]
retain_ground=os.environ.get('A18_ROUTER_RETAIN_GROUND_COPPER')=='1'
if retain_ground:
    text='\n'.join(line.replace('(type route)','(type fix)') if '(net GND)(type 'in line else line for line in text.splitlines())+'\n'
else:
    text='\n'.join(line for line in text.splitlines()if '(net GND)(type 'not in line)+'\n'
allow_reroute=os.environ.get('A18_ROUTER_MOVE_EXISTING_WIRES')=='1'
allow_via_reroute=os.environ.get('A18_ROUTER_MOVE_EXISTING_VIAS')=='1'
movable_nets=set(filter(None,os.environ.get('A18_ROUTER_MOVE_NETS','').split(',')))
if allow_reroute:
    # Freerouting calcFixed maps unrecognized "route" to USER_FIXED.
    # "normal" is its explicit UNFIXED token. Preserve locked copper (fix)
    # and, by default, existing off-pad via locations. An explicit trial
    # option can also move unlocked vias; protected copper remains "fix".
    def movable_wire(line):
        if '(via 'in line and not allow_via_reroute:return False
        match=re.search(r'\(net ("[^"\n]+"|[^\s()]+)\)',line)
        return not movable_nets or bool(match and match[1].strip('"') in movable_nets)
    text='\n'.join(line.replace('(type route)','(type normal)') if movable_wire(line) else line for line in text.splitlines())+'\n'
assert '    (net GND\n'in text,'Keep ground pad ownership in router input'
small='Via[0-1]_450:200_um';large='Via[0-1]_600:300_um'
if '(padstack "'+small+'"'not in text:
    at=text.index('(padstack "'+large+'"');a,z=span(text,at)
    block=text[a:z].replace(large,small).replace(' 600',' 450').replace(' 300',' 200')
    text=text[:z]+'\n    '+block+text[z:]
if '(padstack "'+large+'"'not in text:
    at=text.index('(padstack "'+small+'"');a,z=span(text,at)
    block=text[a:z].replace(small,large).replace(' 450',' 600').replace(' 200',' 300')
    text=text[:z]+'\n    '+block+text[z:]
start=text.index('  (network');a,z=span(text,start);network=text[a:z]
names=set(re.findall(r'(?m)^    \(net ("[^"\n]+"|[^\s()]+)',network))
while '    (class 'in network:
    at=network.index('    (class ');aa,zz=span(network,at);network=network[:at]+network[zz:]
power={'VIN_DC','VIN_FUSED','VIN_PROTECTED','SYS_5V','MODEM_3V8','BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','UPS_SW','BUCK_SW','ESP_SW'}&names
aux={'ESP_3V3','MODEM_1V8'}&names
audio={'SPK_PLUS','SPK_MINUS'}&names
ordinary=names-power-aux-audio-{'GND'}
signal_width=int(os.environ.get('A18_ROUTER_SIGNAL_WIDTH_UM','160'))
power_width=int(os.environ.get('A18_ROUTER_POWER_WIDTH_UM','500'))
assert signal_width>=120 and power_width>=250
classes=[('kicad_default',ordinary,signal_width,150,small),('POWER',power,power_width,200,large),
         ('AUX_POWER',aux,250,150,small),('AUDIO_POWER',audio,400,150,small),('GROUND',{'GND'},200,150,small)]
blocks=['    (class '+name+' '+' '.join(sorted(nets))+' (circuit (use_via "'+via+'")) (rule (width '+str(width)+') (clearance '+str(clearance)+')))'
        for name,nets,width,clearance,via in classes if nets]
network=network.rstrip();assert network.endswith(')')
network=network[:-1]+'\n'+'\n'.join(blocks)+'\n  )'
text=text[:a]+network+text[z:]
(OUT/'signals.dsn').write_text(text,encoding='utf-8')
report={'PCB_sha256':hashlib.sha256(FILE.read_bytes()).hexdigest(),'ground_pin_ownership_preserved':True,
        'actual_ground_copper_retained_as_fixed_obstacles':retain_ground,
        'ordinary_existing_wires_movable':allow_reroute,'existing_via_positions_preserved':not allow_via_reroute,
        'unlocked_ordinary_vias_movable':allow_reroute and allow_via_reroute,
        'movable_wire_nets':sorted(movable_nets) if movable_nets else 'all unlocked wire nets',
        'parser_rule_evidence':'build/cad-tools/freerouting-wiring-bytecode.txt calcFixed: NORMAL=UNFIXED, route=USER_FIXED',
        'ground_planes_excluded_only_from_router_input':True,'skip_argument':['-inc','GROUND'],
        'routing_classes':[{'name':name,'width_um':width,'clearance_um':clearance}for name,nets,width,clearance,via in classes],
        'final_native_DRC_must_connect_all_grounds':True}
(OUT/'exports/router-input-scope.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('Clean candidate exported with real pin ownership; use -inc GROUND, then fill/stitch and native DRC.')
