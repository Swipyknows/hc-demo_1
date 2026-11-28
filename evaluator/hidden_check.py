"""Hidden evaluator: judges the BEHAVIOUR of submitted firmware. The agent never sees this
file or evaluator/cases.json.

Independence: the firmware is rebuilt in a fresh workspace made from the pristine case
sources; only the agent's EDITABLE files (main.c) are taken from its workspace.
"""
import json
import os
import shutil

from tools.target import EDITABLE, NO_FAULT, Target, prepare_workspace

CASES_FILE = os.path.join(os.path.dirname(__file__), "cases.json")


def load_hidden(case_id):
    return json.load(open(CASES_FILE))[case_id]


def check_uart(uart, verify):
    """Return None if the UART output satisfies the hidden condition, else a reason."""
    lines = [l.strip() for l in uart.splitlines()]
    pos = 0
    for want in verify["expect_lines"]:                 # must appear, in this order
        try:
            pos = lines.index(want, pos) + 1
        except ValueError:
            return f"missing or out of order: {want!r}"
    for bad in verify.get("forbid", []):
        if bad in uart:
            return f"forbidden output present: {bad!r}"
    return None


def evaluate(workspace, case_id="bug_001", seconds=3):
    """Returns a dict: verdict (PASS | FAIL | BUILD_FAIL), build, status, uart, reason."""
    verify = load_hidden(case_id)["verify"]
    eval_ws = os.path.join("workspaces", f"eval_{case_id}")
    prepare_workspace(os.path.join("fw", case_id), eval_ws)
    for name in EDITABLE:
        src = os.path.join(workspace, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(eval_ws, name))

    with Target.attach(eval_ws) as t:
        ok, out = t.build()
        if not ok:
            return {"verdict": "BUILD_FAIL", "build": "FAILED", "status": None, "uart": "",
                    "reason": out}
        t.start()
        status = t.run(seconds)
        uart = t.read_uart()

    res = {"verdict": "FAIL", "build": "SUCCESS", "status": status, "uart": uart}
    if status != verify.get("status", NO_FAULT):
        res["reason"] = f"runtime status {status}"
    else:
        res["reason"] = check_uart(uart, verify)
    if res["reason"] is None:
        res["verdict"], res["reason"] = "PASS", "expected behaviour observed"
    return res


def report(res):
    """Human-readable summary in the format used by the project specification."""
    fixed = res["verdict"] == "PASS"
    return "\n".join([
        res["uart"].rstrip(),
        "",
        f"BUILD: {res['build']}",
        f"EXECUTION: {'SUCCESS' if res['status'] == NO_FAULT else res['status'] or 'N/A'}",
        f"BUG STATUS: {'FIXED' if fixed else 'NOT FIXED'}",
        f"EVALUATION: {'PASS' if fixed else 'FAIL'} ({res['reason']})" if not fixed else "EVALUATION: PASS",
    ])
