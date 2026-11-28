# Agentic AI-Based Hardware-Aware Embedded C Debugging Copilot

An AI-powered debugging system that identifies and fixes Embedded C bugs in a
simulated ARM Cortex-M3 environment. The system combines Gemini/LiteLLM,
QEMU, GDB, ARM GCC, and independent firmware verification.

## Overview

The copilot receives firmware source code and a bug description, then:

1. Builds the firmware using ARM GCC.
2. Runs it inside QEMU.
3. Captures UART output and runtime faults.
4. Uses GDB to inspect processor and fault information.
5. Uses an AI agent to diagnose the issue and generate a patch.
6. Requests human approval before changing `main.c`.
7. Rebuilds and reruns the corrected firmware.
8. Independently verifies whether the bug is fixed.

The benchmark contains 10 seeded bugs (`fw/bug_001` … `fw/bug_010`). The demo case,
`bug_001`, is an unregistered function pointer that causes a Cortex-M3 HardFault.
Its expected output is:

```text
boot ok
rx ok
init done
```

## Technology Stack

- **Firmware:** Embedded C
- **Compiler:** ARM GCC
- **Simulator:** QEMU
- **Debugger:** GDB with pygdbmi
- **AI/Backend:** Python, Gemini, LiteLLM
- **RAG:** PyMuPDF, Sentence Transformers (`all-MiniLM-L6-v2`), ChromaDB
- **Environment:** uv
- **Testing:** Pytest
- **Future Interface:** Streamlit

## Architecture

```text
Firmware + Bug Description
          |
          v
ARM GCC -> QEMU -> UART/GDB Evidence
          |
          v
AI Agent + Runtime Analysis
          |
          v
Proposed Patch -> Human Approval
          |
          v
Rebuild -> Execute -> Hidden Evaluation
```

## Repository Structure

```text
agent/
  agent.py            Agent loop and its 9 tools
  analysis.py         Source + runtime evidence report (UART vs expected, fault, source context)
  prompts.py          System prompt and initial observation
  llm.py              Gemini via LiteLLM
rag/
  ingestion.py        PDF -> text -> chunks -> embeddings -> ChromaDB
  retriever.py        Similarity search used by retrieve_docs()
knowledge_base/
  documentation/      Vendor PDFs (git-ignored, see "Knowledge base")
  chroma/             Generated vector index (git-ignored)
evaluator/
  hidden_check.py     Independent verifier (hidden from the agent)
  cases.json          Hidden root causes, reference fixes, verification conditions
  benchmark.py        Validates that every case reproduces and its reference fix passes
fw/
  common/             Shared startup.c, board.h, link.ld, Makefile (read-only for the agent)
  bug_XXX/            main.c (editable) + case.json (bug report, expected output)
tools/
  target.py           QEMU/GDB lifecycle and agent tools
  gdb_session.py      Manual debugging session for one case
tests/                Pytest unit + QEMU integration tests
results/              Benchmark results; results/runs/ holds one JSON per agent run
run_demo.py           Demo entry point
```

## Benchmark

| Case | Category | Symptom in QEMU |
|------|----------|-----------------|
| bug_001 | Pointer error | HardFault (INVSTATE) after `boot ok` |
| bug_002 | Memory error | `log corrupt` |
| bug_003 | Register error | `tick timeout` |
| bug_004 | UART error | no serial output |
| bug_005 | Interrupt error | unhandled SysTick exception, hang |
| bug_006 | Bit manipulation | `led=1 buzzer=0` |
| bug_007 | Buffer error | corrupted FIFO data |
| bug_008 | Initialization error | HardFault (DIVBYZERO) |
| bug_009 | Control-flow error | infinite loop after `boot ok` |
| bug_010 | Timing error | `sensor timeout` |

Each case has a visible `fw/bug_XXX/case.json` (bug report, expected output) and a
hidden entry in `evaluator/cases.json` (root cause, reference patch, verification
condition). Only `main.c` is copied from the agent's workspace into a fresh
evaluation workspace, so the verdict cannot be influenced by other files.

## Debugging Tools (`tools/target.py`)

| Method | Purpose |
|--------|---------|
| `build()` | Compile with ARM GCC |
| `start()` / `stop()` | Boot QEMU halted, attach GDB (free port, connect retry, clean shutdown) |
| `run(seconds)` | Run and return `HARDFAULT`, `UNHANDLED_EXCEPTION` or `NO_FAULT`; CPU is always halted afterwards |
| `read_uart()` | UART output captured from USART1 |
| `gdb_command(cmd)` | Sandboxed GDB access (shell, scripting and file I/O commands are rejected) |
| `registers()` / `backtrace()` | Core registers and call stack |
| `fault_registers()` | Decoded CFSR/HFSR/MMFAR/BFAR, active exception, stacked frame, faulting PC with source line |
| `read_source(path)` / `list_sources()` | Read firmware sources with line numbers |
| `make_patch()` / `apply_patch()` / `revert()` / `total_diff()` | Patch `main.c` only, with diff for approval |
| `rebuild_and_run()` | Rebuild, reboot, run, collect evidence |

## AI Agent

One agent (Gemini via LiteLLM) runs the loop **Observe -> Analyze -> Debug -> Fix -> Verify**:

1. **Observe** (automatic): read `main.c`, build, run in QEMU, and produce the evidence
   report from `agent/analysis.py`.
2. **Analyze / Debug**: the LLM reasons over the evidence and calls tools for more.
3. **Fix**: `apply_patch` with a stated root cause; a human approves every patch.
4. **Verify**: `verify_fix` rebuilds, reruns and checks the expected UART output.
   On failure the agent investigates again.

| Tool | Function |
|------|----------|
| `read_source()` | Read firmware source code |
| `build_firmware()` | Compile firmware |
| `run_firmware()` | Build, run in QEMU, return the analysed evidence report |
| `read_uart()` | Capture UART output |
| `gdb_command()` | Execute a (sandboxed) GDB command |
| `fault_registers()` | Read decoded fault information |
| `retrieve_docs()` | Search the RAG knowledge base |
| `apply_patch()` | Apply a human-approved patch to `main.c` |
| `verify_fix()` | Rebuild and test against the expected output |

Limits: at most 3 failed fix attempts and 25 steps per run. The independent hidden
evaluator then judges the result.

## Knowledge Base (RAG)

The PDFs in `knowledge_base/documentation/` are copyrighted and not committed. Download:

| File | Document |
|------|----------|
| `DUI0552A_cortex_m3_dgug.pdf` | Arm Cortex-M3 Devices Generic User Guide |
| `pm0056-...-programming-manual-...pdf` | ST PM0056 Cortex-M3 programming manual |
| `rm0033-stm32-armbased-32bit.pdf` | ST RM0033 STM32F205 reference manual (relevant chapters only) |
| `apnt209.pdf` | Keil Application Note 209: Cortex-M fault exceptions |
| `DDI0403E_e_armv7m_arm.pdf` | ARMv7-M Architecture Reference Manual (system-level chapters only) |

Build the index once (re-run with `--rebuild` after changing documents):

```bash
uv run python -m rag.ingestion
uv run python -m rag.retriever "CFSR INVSTATE bit meaning"   # test a query
```

## Running the Project

Install the required tools on Ubuntu or WSL2:

```bash
sudo apt install qemu-system-arm gcc-arm-none-eabi gdb-multiarch \
  libnewlib-arm-none-eabi
uv sync
```

Inspect a case manually:

```bash
uv run python -m tools.gdb_session bug_008
```

Validate the benchmark (each bug reproduces, each reference fix passes):

```bash
uv run python -m evaluator.benchmark
```

Run the tests:

```bash
uv run pytest
```

Run the agent with Gemini (any case, default `bug_005`). `MODEL` and `GEMINI_API_KEY`
are read from `.env`:

```bash
uv run python run_demo.py bug_001
```

- `--auto` applies patches without manual approval.
- `--no-rag` disables documentation retrieval.

Each run prints the agent's root cause and the hidden evaluator's verdict, and is saved
to `results/runs/<case>_<timestamp>.json` (patch, verdict, documentation queries, trace).

## Verification

The hidden evaluator rebuilds the firmware, runs it in QEMU, and checks that it
does not fault, prints the expected lines in order, and prints no forbidden output.

- `PASS` — Bug fixed successfully
- `FAIL` — Fault or incorrect behavior remains
- `BUILD_FAIL` — Patched firmware does not compile