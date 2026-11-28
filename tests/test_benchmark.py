"""Integration tests: boot firmware in QEMU and debug it with GDB.
Skipped when the ARM toolchain / QEMU / gdb-multiarch are not installed."""
import shutil

import pytest

from evaluator.benchmark import list_cases, validate_case
from tools.target import HARDFAULT, NO_FAULT, UNHANDLED, Target

pytestmark = pytest.mark.skipif(
    not all(shutil.which(x) for x in ("qemu-system-arm", "arm-none-eabi-gcc", "gdb-multiarch")),
    reason="embedded toolchain not installed")


def test_bug_001_hardfault_evidence(tmp_path):
    with Target("fw/bug_001", str(tmp_path / "ws")) as t:
        assert t.build()[0]
        t.start()
        assert t.run() == HARDFAULT
        assert t.read_uart() == "boot ok\n"
        f = t.fault_registers()
        assert {"INVSTATE", "FORCED"} <= set(f["active_flags"])
        assert f["stop"]["faulting_pc"] == "0x0"
        assert "main.c:" in f["stop"]["caller_location"]
        assert "HardFault_Handler" in t.backtrace()
        assert "pc" in t.registers()


def test_unhandled_exception_is_identified(tmp_path):
    with Target("fw/bug_005", str(tmp_path / "ws")) as t:
        assert t.build()[0]
        t.start()
        assert t.run() == UNHANDLED
        assert t.last_stop["exception"] == "SysTick"


def test_hang_is_halted_for_inspection(tmp_path):
    with Target("fw/bug_009", str(tmp_path / "ws")) as t:
        res = t.rebuild_and_run(seconds=2)
        assert res["status"] == NO_FAULT and res["uart"] == "boot ok\n"
        assert "flush_queue" in t.backtrace() or "transfer_pair" in t.backtrace()


def test_build_failure_is_reported(tmp_path):
    t = Target("fw/bug_001", str(tmp_path / "ws"))
    _, new = t.make_patch("main.c", "  rx_callback();", "  rx_callback() oops;")
    t.apply_patch("main.c", new)
    res = t.rebuild_and_run()
    assert res["build"] == "FAILED" and "error" in res["output"]


@pytest.mark.parametrize("case", list_cases())
def test_case_reproduces_and_reference_fix_passes(case):
    r = validate_case(case)
    assert r["buggy"]["verdict"] != "PASS", r
    assert r["fixed"]["verdict"] == "PASS", r
