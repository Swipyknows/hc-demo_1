"""Unit tests for the debugging tools. No QEMU/GDB needed."""
import json
import os

import pytest

from evaluator.benchmark import list_cases, load_case
from evaluator.hidden_check import check_uart, load_hidden
from tools.target import Target


@pytest.fixture
def t(tmp_path):
    return Target("fw/bug_001", str(tmp_path / "ws"))


def test_workspace_has_common_and_case_files(t):
    assert set(t.list_sources()) >= {"main.c", "startup.c", "board.h", "link.ld", "Makefile"}
    assert not os.path.exists(os.path.join(t.ws, "case.json"))      # metadata not copied


def test_read_source_numbers_lines(t):
    assert t.read_source("main.c", 1, 1) == '1: #include "board.h"'


def test_read_source_rejects_unknown_file(t):
    with pytest.raises(ValueError):
        t.read_source("../evaluator/cases.json")


def test_patch_only_editable_files(t):
    with pytest.raises(ValueError, match="not editable"):
        t.make_patch("startup.c", "Default_Handler", "X")


def test_patch_requires_unique_match(t):
    with pytest.raises(ValueError, match="exactly once"):
        t.make_patch("main.c", "uart_puts", "x")
    with pytest.raises(ValueError, match="empty"):
        t.make_patch("main.c", "", "x")


def test_patch_apply_and_revert(t):
    diff, new = t.make_patch("main.c", "  rx_callback();", "  rx_callback = on_rx;\n  rx_callback();")
    assert "+  rx_callback = on_rx;" in diff
    assert "rx_callback = on_rx" not in t.read_source()                # make_patch does not write
    t.apply_patch("main.c", new, diff)
    assert "rx_callback = on_rx" in t.read_source() and len(t.patches) == 1
    assert "+  rx_callback = on_rx;" in t.total_diff()
    t.revert()
    assert "rx_callback = on_rx" not in t.read_source() and t.total_diff() == ""


@pytest.mark.parametrize("c", ["shell ls", "!ls", "python print(1)", "pipe bt | cat",
                               "thread apply all shell id", "dump memory /tmp/x 0 4",
                               "set logging on", "source x.gdb", "-exec-run", "kill", "file /bin/sh"])
def test_gdb_command_rejects_escapes(t, c):
    assert t.gdb_command(c).startswith("REJECTED")


def test_check_uart_order_and_forbid():
    v = {"expect_lines": ["boot ok", "rx ok"], "forbid": ["HARDFAULT"]}
    assert check_uart("boot ok\nrx ok\n", v) is None
    assert "out of order" in check_uart("rx ok\nboot ok\n", v)
    assert "forbidden" in check_uart("boot ok\nrx ok\nHARDFAULT\n", v)


def test_every_case_has_visible_and_hidden_metadata():
    cases = list_cases()
    assert len(cases) >= 10
    for c in cases:
        vis, hid = load_case(c), load_hidden(c)
        assert vis["id"] == c and vis["bug_report"] and vis["expected_output"]
        assert hid["verify"]["expect_lines"] == vis["expected_output"]
        # the hidden answer must never leak into the files the agent can read
        assert hid["reference_patch"]["new"] not in open(f"fw/{c}/main.c").read()
        assert "root_cause" not in json.dumps(vis)
