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
- **Environment:** uv
- **Future Interface:** Streamlit
- **Future RAG:** ChromaDB, Sentence Transformers, PyMuPDF

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
agent/                AI agent and LLM integration
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
results/              Benchmark / experiment results (JSON)
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

Run the demo with Gemini (any case, default `bug_001`):

```bash
MODEL=gemini/gemini-2.5-flash GEMINI_API_KEY=... \
uv run python3 run_demo.py bug_001
```

Add `--auto` to apply patches without manual approval.

## Verification

The hidden evaluator rebuilds the firmware, runs it in QEMU, and checks that it
does not fault, prints the expected lines in order, and prints no forbidden output.

- `PASS` — Bug fixed successfully
- `FAIL` — Fault or incorrect behavior remains
- `BUILD_FAIL` — Patched firmware does not compile
