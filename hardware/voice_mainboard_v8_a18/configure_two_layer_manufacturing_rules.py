"""Select documented 1oz process rules, retaining broader power clearances.

JLCPCB publishes 0.10/0.10mm for 1oz 1-/2-layer boards. This design uses
0.16mm signal tracks, 0.15mm ordinary clearance and ordinary 0.20mm drills;
switching/input/battery rails retain 0.20mm clearance. No exclusions are added.
"""
from pathlib import Path
import datetime,json,shutil

OUT=Path(__file__).resolve().parent/'two_layer_work'
FILE=OUT/'voice_mainboard_a18_2layer.kicad_pro'
snap=OUT/'iterations'/('before-process-rules-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
snap.mkdir(parents=True);shutil.copy2(FILE,snap/FILE.name)
data=json.loads(FILE.read_text(encoding='utf-8'))
default=next(q for q in data['net_settings']['classes']if q['name']=='Default')
default.update(clearance=.15,track_width=.16,via_diameter=.45,via_drill=.2)
power={**default,'name':'Power','clearance':.2,'track_width':.6,'via_diameter':.6,'via_drill':.3,'priority':0}
data['net_settings']['classes']=[default,power]
power_nets=['VIN_DC','VIN_FUSED','VIN_PROTECTED','SYS_5V','MODEM_3V8','BAT_BOOST_5V','BAT_SENSE_IN','CELL_NEG','UPS_SW','BUCK_SW','ESP_SW']
data['net_settings']['netclass_patterns']=[{'netclass':'Power','pattern':net}for net in power_nets]
assert not data['board']['design_settings'].get('drc_exclusions',[])
FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
report={'source':'https://jlcpcb.com/capabilities/pcb-capabilities','retrieved_at':datetime.datetime.now().astimezone().isoformat(),
 'source_copy':'build/cad-tools/jlc-pcb-capabilities-20261126.html','published_1oz_1_2_layer_minimum_mm':{'track':.1,'spacing':.1},
 'selected_mm':{'signal_track':.16,'ordinary_clearance':.15,'power_clearance':.2,'via_diameter':.45,'via_drill':.2,'hole_clearance':.25,'copper_edge_clearance':.5},
 'power_nets':power_nets,'no_DRC_exclusions_added':True,'domestic_order_process_and_price_confirmation_pending':True,
 'reason':'Allow standard low-voltage signal and ground routing on two layers with margin above published 1oz capability; keep wider switching/input/battery rail separation.'}
(OUT/'exports/manufacturing-rule-basis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Selected 0.15mm ordinary / 0.20mm power clearance; unchanged pads and 0.20mm ordinary drills.')
