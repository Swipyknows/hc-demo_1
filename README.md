# Embedded debugging copilot: starter (Milestones 1 and 2)

Install (Ubuntu or WSL2):
  sudo apt install qemu-system-arm gcc-arm-none-eabi gdb-multiarch libnewlib-arm-none-eabi
  pip install -r requirements.txt

Milestone 1 (QEMU + GDB reads the fault):   python3 tools/gdb_session.py
Milestone 2 (full agent loop, real LLM):    MODEL=gemini/gemini-2.5-flash GEMINI_API_KEY=... python3 run_demo.py
   add --auto to skip the human patch-approval prompt.
   Local free alternative: MODEL=ollama/qwen2.5-coder:7b

Layout
  fw/          faulty firmware (seeded bug: NULL callback). The agent works on a copy in workspaces/
  tools/       Target class = QEMU + GDB + build + patch tools
  agent/       llm.py (LiteLLM wrapper), agent.py (loop, tool schemas, approval gate, JSONL trace)
  evaluator/   hidden_check.py: judges behaviour (needs 'boot ok', 'rx ok', 'init done', no fault)
Outcomes: PASS | INT (fault persists or behaviour wrong) | BUILD_FAIL | NONE (never submitted)
