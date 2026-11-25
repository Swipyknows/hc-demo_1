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

The current prototype uses one seeded bug: an unregistered function pointer that
causes a Cortex-M3 HardFault. The expected output is:

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
agent/       AI agent and LLM integration
evaluator/   Independent verification
fw/          Seeded firmware source
tools/       QEMU, GDB, build, and patch tools
run_demo.py  Demo entry point
trace.jsonl  Agent execution trace
```

## Running the Project

Install the required tools on Ubuntu or WSL2:

```bash
sudo apt install qemu-system-arm gcc-arm-none-eabi gdb-multiarch \
  libnewlib-arm-none-eabi
uv sync
```

Run the demo with Gemini:

```bash
MODEL=gemini/gemini-2.5-flash GEMINI_API_KEY=... \
uv run python3 run_demo.py
```

Add `--auto` to apply patches without manual approval:

```bash
uv run python3 run_demo.py --auto
```

## Verification

The evaluator checks whether the firmware builds, runs without a fault, and prints
all required UART messages.

- `PASS` — Bug fixed successfully
- `INT` — Fault or incorrect behavior remains
- `BUILD_FAIL` — Patched firmware does not compile
- `NONE` — Agent did not submit a fix
