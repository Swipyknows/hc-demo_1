"""Usage:  python3 run_demo.py [bug_XXX] [--auto]

MODEL and GEMINI_API_KEY are read from the environment or from .env (see .env.example).
"""
import json
import os
import sys
import time

if os.path.exists(".env"):                     # minimal .env loader; real env vars win
    for line in open(".env"):
        k, sep, v = line.strip().partition("=")
        if sep and not k.startswith("#"):
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from agent.agent import run_agent
from agent.llm import litellm_chat
from evaluator.benchmark import load_case
from evaluator.hidden_check import evaluate, report
from tools.target import Target

args = [a for a in sys.argv[1:] if not a.startswith("--")]
case = load_case(args[0] if args else "bug_005")
BUG = (f"{case['bug_report']} Expected serial output: "
       + ", ".join(repr(l) for l in case["expected_output"]) + ".")


def approve(diff):
    if "--auto" in sys.argv:
        return True
    print(diff)
    return input("Apply this patch? [y/N] ").lower() == "y"


def save_run(record):
    """Store one demo run as results/runs/<case>_<timestamp>.json."""
    os.makedirs("results/runs", exist_ok=True)
    path = f"results/runs/{case['id']}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        record["trace"] = [json.loads(l) for l in open("trace.jsonl")]
    except (OSError, ValueError):
        record["trace"] = []
    json.dump(record, open(path, "w"), indent=2)
    print(f"\nRun saved to {path}")


record = {"case": case["id"], "model": os.environ.get("MODEL"), "bug_report": BUG,
          "started": time.strftime("%Y-%m-%d %H:%M:%S")}
t0 = time.time()
t = Target(f"fw/{case['id']}")
try:
    res = run_agent(t, litellm_chat, BUG, approve=approve)
except Exception as e:                # record failed runs too (e.g. API errors)
    record.update(error=f"{type(e).__name__}: {e}", seconds=round(time.time() - t0, 1))
    save_run(record)
    raise
finally:
    t.stop()          # always clean up, even if the LLM call crashes
print(res)
print("\n===== HIDDEN EVALUATOR =====")
ev = evaluate(t.ws, case["id"])
print(report(ev))
record.update(agent=res, patch=t.total_diff(), seconds=round(time.time() - t0, 1),
              evaluation={k: ev[k] for k in ("verdict", "build", "status", "uart", "reason")})
save_run(record)
