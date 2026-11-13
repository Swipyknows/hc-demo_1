"""Milestone 1 demo: run from repo root:  make -C fw && python3 tools/gdb_session.py"""
import sys; sys.path.insert(0, ".")
from tools.target import Target
t = Target(); ok, out = t.build(); assert ok, out
t.start(); print("status:", t.run()); print("UART:", t.read_uart().strip().replace("\n", " | "))
print("Fault registers:", t.fault_registers()); t.stop()
