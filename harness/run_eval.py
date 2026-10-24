"""Runs every attack and legitimate task against each setup and writes harness/results/results.json.
Usage:  python -m harness.run_eval
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from gasentra.cases import ATTACKS, LEGIT
from gasentra.config import Config
from gasentra.executors import GatewayExecutor, PatternDLPExecutor, UnguardedExecutor
from gasentra.gateway import Gateway
from gasentra.scripted import ScenarioRunner
from gasentra.store import Store

RESULTS = Path(__file__).resolve().parent / "results" / "results.json"
CONFIGS = [
    ("no_guard", "No guard", None),
    ("pattern_dlp", "Pattern DLP only (our emulation)", None),
    ("gasentra_careful", "GASENTRA, careful approver (rejects held actions)", "reject"),
    ("gasentra_careless", "GASENTRA, careless approver (approves everything)", "approve"),
]


def run_case(case, config_id, approver, cfg):
    store = Store(":memory:")
    for e in case["inbox"]:
        store.add_email(e["sender"], e["subject"], e["body"], scenario=case["id"])
    if config_id == "no_guard":
        ex = UnguardedExecutor(store, cfg, scenario=case["id"])
    elif config_id == "pattern_dlp":
        ex = PatternDLPExecutor(store, cfg, scenario=case["id"])
    else:
        ex = GatewayExecutor(Gateway(store, cfg), scenario=case["id"])
    ex.start()
    runner = ScenarioRunner(case, ex, cfg, approver=approver or "reject").run()
    sessions = [store.get_session(s) for s in ex.sessions]
    return runner.records, any(s["frozen"] for s in sessions)


def summarize_attack(records, frozen):
    harmful = [r for r in records if r["harmful"]]
    executed_silent = any(r["outcome"] == "executed" for r in harmful)
    executed_after = any(r["outcome"] == "executed_after_approval" for r in harmful)
    held = any(r["decision"] == "hold" or r["outcome"] in ("rejected_by_human", "executed_after_approval")
               for r in harmful)
    if executed_silent:
        status = "SILENT LEAK/TAMPER"
    elif executed_after:
        status = "executed after approval"
    elif frozen:
        status = "frozen"
    elif held:
        status = "held and rejected"
    elif harmful:
        status = "blocked"
    else:
        status = "no harmful call made"
    return {"status": status, "silent": executed_silent, "after_approval": executed_after,
            "held": held, "frozen": frozen, "harmful_calls": len(harmful),
            "rules": [r["rule"] for r in harmful]}


def summarize_legit(case, records, frozen):
    key = [r for r in records if r["key"]]
    r = key[-1] if key else None
    if r is None:
        return {"status": "no key call", "completed": False, "approval_needed": False, "false_block": True}
    completed = r["outcome"] in ("executed", "executed_after_approval")
    approval = r["decision"] == "allow" and r["outcome"] == "executed_after_approval" or r["outcome"] in (
        "rejected_by_human", "held")
    false_block = r["outcome"] in ("blocked", "frozen")
    return {"status": r["outcome"], "completed": completed, "approval_needed": approval,
            "false_block": false_block, "rule": r["rule"]}


def main():
    cfg = Config()
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "notes": ["All data is synthetic.",
                     "Pattern DLP and No guard are our own simplified emulations, not real products.",
                     "A careful approver rejects every held action; a careless approver approves them all."],
           "configs": [], "attack_rows": [], "legit_rows": []}
    for cid, label, approver in CONFIGS:
        a_sum = {"total": 0, "silent": 0, "after_approval": 0, "held": 0, "blocked": 0, "frozen": 0}
        l_sum = {"total": 0, "completed": 0, "false_blocks": 0, "approvals": 0,
                 "sensitive_total": 0, "sensitive_approvals": 0, "other_total": 0, "other_approvals": 0}
        for case in ATTACKS:
            records, frozen = run_case(case, cid, approver, cfg)
            s = summarize_attack(records, frozen)
            a_sum["total"] += 1
            a_sum["silent"] += s["silent"]
            a_sum["after_approval"] += s["after_approval"]
            a_sum["held"] += s["held"]
            a_sum["frozen"] += s["frozen"]
            a_sum["blocked"] += (not s["silent"] and not s["after_approval"] and not s["held"])
            out["attack_rows"].append({"config": cid, "id": case["id"], "class": case["class"],
                                       "title": case["title"], **s})
        for case in LEGIT:
            records, frozen = run_case(case, cid, approver, cfg)
            s = summarize_legit(case, records, frozen)
            l_sum["total"] += 1
            l_sum["completed"] += s["completed"]
            l_sum["false_blocks"] += s["false_block"]
            l_sum["approvals"] += s["approval_needed"]
            bucket = "sensitive" if case["touches_sensitive"] else "other"
            l_sum[bucket + "_total"] += 1
            l_sum[bucket + "_approvals"] += s["approval_needed"]
            out["legit_rows"].append({"config": cid, "id": case["id"], "title": case["title"],
                                      "expected": case["expect"], "touches_sensitive": case["touches_sensitive"], **s})
        l_sum["approvals_per_100"] = round(100 * l_sum["approvals"] / l_sum["total"], 1)
        out["configs"].append({"id": cid, "label": label, "attacks": a_sum, "legit": l_sum})
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    res = main()
    print("%-52s %7s %7s %7s | %6s %6s %6s" % ("setup", "silent", "afterAp", "frozen", "legit", "falseB", "appr/100"))
    for c in res["configs"]:
        a, l = c["attacks"], c["legit"]
        print("%-52s %3d/%-3d %7d %7d | %3d/%-2d %6d %8s" % (c["label"][:52], a["silent"], a["total"], a["after_approval"],
                                                           a["frozen"], l["completed"], l["total"], l["false_blocks"],
                                                           l["approvals_per_100"]))
    print("Saved", RESULTS)
