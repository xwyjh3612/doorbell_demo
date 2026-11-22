"""Reproduce a cost scenario; does not modify the electrical design or active BOM."""
import hashlib
import json
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parent
baseline = json.loads((ROOT / "bom-budget.json").read_text(encoding="utf-8"))
research_path = ROOT / "低价替代料核查.json"
research = json.loads(research_path.read_text(encoding="utf-8"))
installed = {p["ref"]: p for p in baseline["parts"] if p["populated"]}
prices = {ref: D(str(p["unit_cny"])) for ref, p in installed.items()}


def subtotal(refs):
    return sum((prices[ref] for ref in refs), D(0))


old_ups = {ref for ref, p in installed.items() if p["group"].startswith("02 ")}
old_boost = {"U9", "L3", "C41", "C42", "C43", "C45", "R40", "R41"}
input_front = {"J1", "F1", "Q6", "R32"}
assert not old_ups & old_boost
assert not (old_ups | old_boost) & input_front
base = subtotal(installed)
assert base == D(str(baseline["board_material_per_board_cny"]))
candidates = {p["role"]: p for p in research["candidates"]}
preferred_roles = ("sim_socket", "sim_esd_array", "esp_buck")
preferred_saving = sum(
    (D(str(candidates[r]["conditional_difference_per_board_cny"])) for r in preferred_roles), D(0)
)
modem_saving = D(str(candidates["modem_buck_conditional"]["conditional_difference_per_board_cny"]))
ups_allowance = D("5.00")
processing = {"bare_PCB": D("2.50"), "SMT_THT": D("3.50"), "loss_programming_test": D("2.50")}
overhead = sum(processing.values(), D(0))
retained_modem_buck = base - preferred_saving - subtotal(old_ups) - subtotal(old_boost) + ups_allowance
cheap_modem_buck = retained_modem_buck - modem_saving


def scenario(material, roles, front_in_ups=False):
    return {
        "material_per_board_cny": material,
        "assembled_allowance_per_board_cny": material + overhead,
        "assembled_allowance_1000_boards_cny": (material + overhead) * 1000,
        "replacement_roles": roles,
        "input_front_end_in_5_cny": front_in_ups,
        "production_qualified": False,
    }


breakdown = {
    "ESP32-S3 module": D("12"),
    "ML307C-DL module": D("10"),
    "5V UPS integrated materials": ups_allowance,
    "input connector protection and complete 4G buck": D("5.51220") - modem_saving,
    "ESP 3.3V amp and audio interface": D("9.93110") - subtotal(old_boost) - D(str(candidates["esp_buck"]["conditional_difference_per_board_cny"])),
    "modem UART reset and decoupling": D("13.81290") - D("10"),
    "ESP buttons interfaces and ADC": D("14.32670") - D("12"),
    "SIM RF and USB interface": D("6.47000") - sum((D(str(candidates[r]["conditional_difference_per_board_cny"])) for r in preferred_roles[:2]), D(0)),
}
assert sum(breakdown.values(), D(0)) == cheap_modem_buck
assert retained_modem_buck == D("44.78531")
assert cheap_modem_buck == D("42.40246")

report = {
    "date": baseline["date"],
    "quantity": 1000,
    "currency": "CNY",
    "baseline_PCB_sha256": baseline["PCB_sha256"],
    "baseline_budget_sha256": hashlib.sha256((ROOT / "bom-budget.json").read_bytes()).hexdigest(),
    "candidate_research_sha256": hashlib.sha256(research_path.read_bytes()).hexdigest(),
    "active_BOM_changed": False,
    "supplier_final_quote_obtained": False,
    "basis": "User ML307=10, ESP=12, integrated system5V/UPS materials=5; other prices inherit baseline and researched candidate tiers. PCB/assembly/test are unquoted allowances.",
    "ups_assumed_scope": "Includes charge, battery undervoltage/isolation, automatic source switching, system5V boost and their passives/connectors; excludes input jack/protection, modem3.8V and ESP3.3V bucks, amplifier and ESP ADC. Actual UPS design unknown.",
    "removed_blocks": [
        {"role": "old_charge_battery_UV_mux", "refs": sorted(old_ups), "material_per_board_cny": subtotal(old_ups)},
        {"role": "old_standalone_audio5V_boost", "refs": sorted(old_boost), "material_per_board_cny": subtotal(old_boost)},
    ],
    "input_front_end": {"refs": sorted(input_front), "material_per_board_cny": subtotal(input_front)},
    "baseline_material_per_board_cny": base,
    "preferred_candidate_saving_cny": preferred_saving,
    "conditional_modem_buck_saving_cny": modem_saving,
    "manufacturing_allowances_per_board_cny": processing,
    "scenarios": {
        "retain_original_modem_buck": scenario(retained_modem_buck, list(preferred_roles)),
        "conditional_cheaper_modem_buck": scenario(cheap_modem_buck, list(preferred_roles) + ["modem_buck_conditional"]),
        "conditional_input_front_also_in_ups5": scenario(cheap_modem_buck - subtotal(input_front), list(preferred_roles) + ["modem_buck_conditional"], True),
    },
    "cheaper_modem_scenario_material_breakdown_cny": breakdown,
    "limitations": [
        "TPS563201 minimum input4.5V is not guaranteed after protection drops at original external4.5V lower boundary; design changes and load validation required.",
        "UPS actual components, continuous/peak output and switching behavior not yet identified; no new power PCB has been validated.",
        "Candidate changes require footprint/layout and passives review; unchanged supporting-passive costs are provisional.",
        "Existing installed component/pad counts belong to baseline, not this unimplemented scenario.",
        "Tax/freight, procurement minimums, sourcing/authenticity and assembly factory quote not established.",
    ],
    "excludes": baseline["production_cost_constraint"]["excludes"],
}


def numeric(value):
    if isinstance(value, D):
        return float(value)
    if isinstance(value, dict):
        return {k: numeric(v) for k, v in value.items()}
    if isinstance(value, list):
        return [numeric(v) for v in value]
    return value


(ROOT / "ups5-budget.json").write_text(json.dumps(numeric(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(numeric(report["scenarios"]), ensure_ascii=False, indent=2))
