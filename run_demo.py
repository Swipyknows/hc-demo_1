"""Usage:  MODEL=gemini/gemini-2.5-flash GEMINI_API_KEY=... python3 run_demo.py [--auto]"""
import sys
from tools.target import Target
from agent.agent import run_agent
from agent.llm import litellm_chat
from evaluator.hidden_check import evaluate

BUG = ("After printing 'boot ok' the board stops responding on serial. "
       "Expected serial output: 'boot ok', 'rx ok', 'init done'.")

def approve(diff):
    if "--auto" in sys.argv:
        return True
    print(diff)
    return input("Apply this patch? [y/N] ").lower() == "y"

t = Target()
try:
    res = run_agent(t, litellm_chat, BUG, approve=approve)
finally:
    t.stop()          # always clean up, even if the LLM call crashes
print(res)
print("HIDDEN EVALUATOR:", evaluate(t.ws))
