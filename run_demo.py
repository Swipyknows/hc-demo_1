"""Usage:  MODEL=gemini/gemini-2.5-flash GEMINI_API_KEY=... python3 run_demo.py [bug_001] [--auto]"""
import sys

from agent.agent import run_agent
from agent.llm import litellm_chat
from evaluator.benchmark import load_case
from evaluator.hidden_check import evaluate, report
from tools.target import Target

args = [a for a in sys.argv[1:] if not a.startswith("--")]
case = load_case(args[4] if args else "bug_005")
BUG = (f"{case['bug_report']} Expected serial output: "
       + ", ".join(repr(l) for l in case["expected_output"]) + ".")


def approve(diff):
    if "--auto" in sys.argv:
        return True
    print(diff)
    return input("Apply this patch? [y/N] ").lower() == "y"


t = Target(f"fw/{case['id']}")
try:
    res = run_agent(t, litellm_chat, BUG, approve=approve)
finally:
    t.stop()          # always clean up, even if the LLM call crashes
print(res)
print("\n===== HIDDEN EVALUATOR =====")
print(report(evaluate(t.ws, case["id"])))
