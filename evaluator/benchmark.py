"""Benchmark validation: every case must (1) reproduce its bug and (2) be fixed by its
hidden reference patch. Run this after adding or changing a case.

Usage:  python -m evaluator.benchmark [bug_001 bug_002 ...]
Writes results/benchmark_validation.json
"""
import json
import os
import sys
import time

from evaluator.hidden_check import evaluate, load_hidden
from tools.target import Target

FW_DIR = "fw"


def list_cases():
    return sorted(d for d in os.listdir(FW_DIR) if d.startswith("bug_"))


def load_case(case_id):
    """Visible case information (what a user / the agent is given)."""
    return json.load(open(os.path.join(FW_DIR, case_id, "case.json")))


def validate_case(case_id):
    t0 = time.time()
    ws = os.path.join("workspaces", f"bench_{case_id}")
    t = Target(os.path.join(FW_DIR, case_id), ws)
    buggy = evaluate(ws, case_id)

    p = load_hidden(case_id)["reference_patch"]
    diff, new_text = t.make_patch(p["file"], p["old"], p["new"])
    t.apply_patch(p["file"], new_text, diff)
    fixed = evaluate(ws, case_id)

    ok = buggy["verdict"] != "PASS" and fixed["verdict"] == "PASS"
    return {"case": case_id, "valid": ok, "seconds": round(time.time() - t0, 1),
            "buggy": {k: buggy[k] for k in ("verdict", "status", "uart", "reason")},
            "fixed": {k: fixed[k] for k in ("verdict", "status", "uart", "reason")}}


def main(cases):
    results = []
    for c in cases:
        r = validate_case(c)
        results.append(r)
        print(f"{c}  {'VALID' if r['valid'] else 'INVALID':8}"
              f" buggy={r['buggy']['verdict']:<10} ({r['buggy']['reason']})"
              f"  ->  reference fix={r['fixed']['verdict']}  [{r['seconds']}s]", flush=True)
    os.makedirs("results", exist_ok=True)
    json.dump(results, open("results/benchmark_validation.json", "w"), indent=2)
    n = sum(r["valid"] for r in results)
    print(f"\n{n}/{len(results)} cases valid")
    return n == len(results)


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1:] or list_cases()) else 1)
