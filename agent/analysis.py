"""Source-code and runtime analysis: turns raw build/QEMU/GDB output into one evidence
report for the agent (Observe step) and for the dashboard.

analyze(target, expected_lines) builds, boots and runs the firmware, then leaves the CPU
halted so the agent can keep investigating with GDB.
"""
import re

from tools.target import NO_FAULT

LOC_RE = re.compile(r"(\w+\.[ch]):(\d+)")


def compare_uart(uart, expected):
    """Compare UART output with the expected lines (in order)."""
    got = [l.strip() for l in uart.splitlines() if l.strip()]
    matched, pos = [], 0
    for want in expected:
        if want in got[pos:]:
            pos = got.index(want, pos) + 1
            matched.append(want)
        else:
            break
    missing = [l for l in expected if l not in matched]
    return {
        "ok": not missing,
        "matched": matched,
        "missing": missing,
        "first_missing": missing[0] if missing else None,
        "unexpected": [l for l in got if l not in expected],
        "last_line": got[-1] if got else None,
    }


def source_context(t, location, radius=4):
    """'main.c:15' (anywhere in `location`) -> numbered source lines around it, marked."""
    m = LOC_RE.search(location or "")
    if not m:
        return None
    name, line = m.group(1), int(m.group(2))
    try:
        text = t.read_source(name, max(1, line - radius), line + radius)
    except ValueError:
        return None
    marked = [("> " if l.split(":", 1)[0] == str(line) else "  ") + l for l in text.splitlines()]
    return {"file": name, "line": line, "code": "\n".join(marked)}


def compiler_warnings(output):
    return [l for l in output.splitlines() if "warning:" in l or "error:" in l]


def analyze(t, expected, seconds=3):
    """Build + run + collect + interpret. Returns a dict (see format_report)."""
    ok, out = t.build()
    r = {"build": "OK" if ok else "FAILED", "warnings": compiler_warnings(out)}
    if not ok:
        r["compiler_output"] = out
        return r

    t.start()
    r["status"] = t.run(seconds)
    r["uart"] = t.read_uart()
    r["uart_check"] = compare_uart(r["uart"], expected)
    stop = t.last_stop or {}
    r["backtrace"] = t.backtrace()

    if r["status"] != NO_FAULT:
        f = t.fault_registers()
        r["fault"] = {k: f[k] for k in ("CFSR", "HFSR", "active_flags", "MMFAR", "BFAR") if k in f}
        r["fault"].update({k: stop[k] for k in ("exception", "faulting_pc", "faulting_location",
                                                 "caller_lr", "caller_location") if k in stop})
        r["context"] = [c for c in (source_context(t, stop.get("faulting_location")),
                                    source_context(t, stop.get("caller_location"))) if c]
    else:
        # No exception: the CPU was halted at the end of the time window. If output is
        # incomplete, where it was halted shows where the program is stuck (hang) or idle.
        r["halted_at"] = stop.get("location")
        ctx = source_context(t, stop.get("location"))
        r["context"] = [ctx] if ctx else []
    return r


def format_report(r, expected):
    """Compact, readable text version of an analysis for the LLM."""
    lines = [f"BUILD: {r['build']}"]
    if r["warnings"]:
        lines += ["COMPILER WARNINGS:"] + [f"  {w}" for w in r["warnings"]]
    if r["build"] != "OK":
        lines += ["COMPILER OUTPUT:", r.get("compiler_output", "")]
        return "\n".join(lines)
    c = r["uart_check"]
    lines += [f"RUN STATUS: {r['status']}",
              f"UART OUTPUT: {r['uart']!r}",
              f"EXPECTED LINES: {expected}",
              "UART CHECK: " + ("all expected lines present" if c["ok"] else
                                f"missing {c['missing']} (output stops after {c['last_line']!r})")]
    if c["unexpected"]:
        lines.append(f"UNEXPECTED UART LINES: {c['unexpected']}")
    if "fault" in r:
        lines.append("FAULT: " + ", ".join(f"{k}={v}" for k, v in r["fault"].items()))
    if r.get("halted_at"):
        lines.append(f"CPU HALTED AT (end of run window): {r['halted_at']}")
    lines += ["BACKTRACE:", r["backtrace"] or "(none)"]
    for ctx in r.get("context", []):
        lines += [f"SOURCE AROUND {ctx['file']}:{ctx['line']}:", ctx["code"]]
    return "\n".join(lines)
