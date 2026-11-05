import json
import random
from datetime import datetime, timedelta
import sys

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 42
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/scenarios.json"
PER_CAUSE = int(sys.argv[3]) if len(sys.argv) > 3 else 5
random.seed(SEED)

CELL_POOL = [f"cell_{n}" for n in range(1, 21)]
BASE_TIME = datetime(2026, 11, 1, 10, 0, 0)


def healthy_kpis():
    return {
        "ho_exec_sr_pct": round(random.uniform(98.5, 99.9), 1),
        "ho_prep_sr_pct": round(random.uniform(98.5, 99.9), 1),
        "rlf_per_hour": random.randint(0, 3),
        "rsrp_avg_dbm": random.randint(-92, -80),
        "sinr_dl_avg_db": round(random.uniform(14, 22), 1),
        "ul_sinr_avg_db": round(random.uniform(10, 18), 1),
        "pusch_bler_pct": round(random.uniform(1, 5), 1),
        "phr_avg_db": round(random.uniform(8, 18), 1),
        "prb_util_dl_pct": random.randint(25, 60),
    }


def apply_coverage_edge(kpis, serving, target, other):
    kpis[serving].update({
        "ho_exec_sr_pct": round(random.uniform(70, 85), 1),
        "rsrp_avg_dbm": random.randint(-118, -108),
        "sinr_dl_avg_db": round(random.uniform(0, 6), 1),
        "rlf_per_hour": random.randint(15, 40),
    })


def apply_missing_neighbor(kpis, serving, target, other):
    kpis[serving].update({
        "ho_prep_sr_pct": round(random.uniform(60, 80), 1),
        "ho_exec_sr_pct": round(random.uniform(85, 92), 1),
    })


def apply_late_trigger(kpis, serving, target, other):
    kpis[serving].update({
        "ho_exec_sr_pct": round(random.uniform(78, 88), 1),
        "rlf_per_hour": random.randint(25, 50),
        "rsrp_avg_dbm": random.randint(-100, -92),
    })


def apply_target_overload(kpis, serving, target, other):
    kpis[target]["prb_util_dl_pct"] = random.randint(91, 99)
    kpis[serving]["ho_prep_sr_pct"] = round(random.uniform(70, 85), 1)


def apply_xn_transport(kpis, serving, target, other):
    kpis[serving]["ho_prep_sr_pct"] = round(random.uniform(40, 70), 1)


def apply_ul_power(kpis, serving, target, other):
    kpis[serving].update({
        "ul_sinr_avg_db": round(random.uniform(0, 5), 1),
        "pusch_bler_pct": round(random.uniform(15, 30), 1),
        "phr_avg_db": round(random.uniform(-6, -1), 1),
        "ho_exec_sr_pct": round(random.uniform(82, 90), 1),
        "rlf_per_hour": random.randint(10, 25),
    })


CAUSES = {
    "coverage_edge": {
        "apply": apply_coverage_edge,
        "fix": "Improve coverage at the cell edge: adjust antenna tilt or power, or add a cell.",
        "logs": [
            "WARN MeasReport: serving {serving} RSRP={rsrp_low}dBm below -108dBm, no target above A3 threshold",
            "WARN RLF detected for UE {ue}, cause=out-of-sync, serving {serving}",
            "WARN Serving cell SINR below 3dB for UE {ue} at cell edge of {serving}",
        ],
    },
    "missing_neighbor": {
        "apply": apply_missing_neighbor,
        "fix": "Add the missing neighbor relation (target PCI) to the NRT of the serving cell.",
        "logs": [
            "ERROR HO prep failed: target PCI {pci} not found in NRT of {serving}",
            "WARN ANR: unknown PCI {pci} reported in MeasReport by UE {ue}, no neighbor relation",
        ],
    },
    "late_trigger": {
        "apply": apply_late_trigger,
        "fix": "Reduce A3 offset and time-to-trigger so handover starts earlier.",
        "logs": [
            "ERROR T310 expired before HO command, UE {ue} context released on {serving}",
            "WARN A3 event triggered late: offset=6dB TTT=640ms, serving RSRP at trigger={rsrp_low}dBm",
        ],
    },
    "target_overload": {
        "apply": apply_target_overload,
        "fix": "Relieve the target cell: load balancing, offload users, or add capacity.",
        "logs": [
            "ERROR HO prep rejected by {target}: cause=radio-resources-not-available",
            "WARN Admission control reject on {target}, DL PRB utilization {prb}%",
        ],
    },
    "xn_transport": {
        "apply": apply_xn_transport,
        "fix": "Fix the Xn transport path: check SCTP association, routing and backhaul.",
        "logs": [
            "ERROR SCTP association to {target} timeout, Xn link down",
            "ERROR Xn HO prep timeout (TXnRELOCprep expired) toward {target}",
            "ERROR Xn setup failure toward {other}: transport network layer unreachable",
        ],
    },
    "ul_power_control": {
        "apply": apply_ul_power,
        "fix": "Retune UL power control (P0 nominal / alpha) so UEs are not power limited.",
        "logs": [
            "WARN UE {ue} at max Tx power (PHR<0), PUSCH SINR={ul_sinr}dB on {serving}",
            "ERROR RLF cause=UL sync loss for UE {ue}, serving {serving}, DL RSRP normal",
            "WARN PUSCH BLER above 15% on {serving}, UL power headroom negative",
        ],
    },
}

NOISE = [
    "INFO RRC reconfiguration complete for UE {ue}",
    "INFO Handover completed {serving}->{target} for UE {ue}",
    "INFO PDU session modify ok for UE {ue}",
    "DEBUG scheduler tick ok on {serving}",
    "INFO Periodic measurement report received from UE {ue}",
    "DEBUG PM counter collection finished for {serving}",
]

SYMPTOMS = [
    "Handover failures have increased on {serving} in the last hour. What is the root cause?",
    "Users report dropped calls around {serving}. Diagnose the problem.",
    "KPI alarm raised on {serving}: handover performance degraded. Find the cause and recommend a fix.",
]


def render(template, ctx):
    return template.format(**ctx, ue=random.randint(1000, 9999))


def build_scenario(idx, cause_key, ambiguous):
    cause = CAUSES[cause_key]
    serving, target, other = random.sample(CELL_POOL, 3)
    ctx = {
        "serving": serving,
        "target": target,
        "other": other,
        "pci": random.randint(1, 1007),
        "rsrp_low": random.randint(-118, -110),
        "prb": random.randint(91, 99),
        "ul_sinr": round(random.uniform(0, 5), 1),
    }

    kpis = {c: healthy_kpis() for c in (serving, target, other)}
    cause["apply"](kpis, serving, target, other)

    templates = [random.choice(cause["logs"]) for _ in range(random.randint(5, 8))]
    if ambiguous:
        other_key = random.choice([k for k in CAUSES if k != cause_key])
        templates += random.sample(CAUSES[other_key]["logs"], 2)
    templates += [random.choice(NOISE) for _ in range(random.randint(12, 18))]

    entries = []
    for t in templates:
        when = BASE_TIME + timedelta(seconds=random.randint(0, 3600))
        entries.append((when, render(t, ctx)))
    entries.sort(key=lambda e: e[0])
    logs = [f"{when:%H:%M:%S} {text}" for when, text in entries]

    return {
        "id": f"S{idx:02d}",
        "symptom": random.choice(SYMPTOMS).format(serving=serving),
        "serving_cell": serving,
        "kpis": kpis,
        "logs": logs,
        "ambiguous": ambiguous,
        "ground_truth": {"root_cause": cause_key, "fix": cause["fix"]},
    }


def main():
    scenarios = []
    idx = 1
    for cause_key in CAUSES:
        for i in range(PER_CAUSE):
            scenarios.append(build_scenario(idx, cause_key, ambiguous=(i % 5 == 4)))
            idx += 1
    random.shuffle(scenarios)
    with open(OUT, "w") as f:
        json.dump(scenarios, f, indent=2)
    print(f"Wrote {len(scenarios)} scenarios to {OUT} (seed {SEED})")
    
if __name__ == "__main__":
    main()