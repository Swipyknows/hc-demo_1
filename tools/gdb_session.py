"""Manual QEMU + GDB debugging session for one benchmark case.

Usage:  python -m tools.gdb_session [bug_001]
"""
import json
import sys

from tools.target import Target

case = sys.argv[1] if len(sys.argv) > 1 else "bug_001"


def section(title):
    print(f"\n========== {title} ==========")


with Target(f"fw/{case}", f"workspaces/session_{case}") as t:
    ok, out = t.build()
    section("BUILD")
    print("SUCCESS" if ok else "FAILED")
    print(out)
    if not ok:
        sys.exit(1)

    section("EXECUTION")
    t.start()
    print("Status:", t.run())

    section("UART OUTPUT")
    print(t.read_uart())

    section("FAULT REGISTERS")
    print(json.dumps(t.fault_registers(), indent=2))

    section("CPU REGISTERS")
    print(t.cmd("info registers"))

    section("BACKTRACE")
    print(t.backtrace())
