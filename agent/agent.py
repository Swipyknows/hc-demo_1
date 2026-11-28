"""The agent loop: Observe -> Hypothesize -> Act (tool) -> Verify -> repeat,
until the model calls submit_fix or the step limit is reached."""
import json
import time

SYSTEM = (
    "You are an embedded-firmware debugging agent for a Cortex-M3 (STM32-class) target "
    "running in QEMU. Work in a loop: read the evidence, state a hypothesis, use a tool to "
    "test it, then fix and verify. Rules: only patch main.c; make the smallest fix that "
    "restores the behaviour described in the bug report; always call rebuild_and_run after a "
    "patch and check the UART output and status; call submit_fix only when your own "
    "verification shows the fault is gone and the expected behaviour appears. "
    "Run status is HARDFAULT, UNHANDLED_EXCEPTION (an exception had no handler), or NO_FAULT "
    "(still running at the end of the time window; it may still be hung or print wrong data). "
    "startup.c, board.h and link.ld are read-only but may be read."
)


def _tool(name, desc, props, required=()):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(required)},
        },
    }


def _s(desc):
    return {"type": "string", "description": desc}


TOOLS = [
    _tool("gdb", "Run one GDB command on the halted target, e.g. bt, info registers, x/8wx $sp, list.",
          {"command": _s("GDB command")}, ["command"]),
    _tool("fault_registers", "Decode the Cortex-M fault status registers (CFSR/HFSR).", {}),
    _tool("read_uart", "Return everything the firmware has printed on its serial port.", {}),
    _tool("read_source", "Read lines of a source file (main.c, startup.c, board.h, link.ld), "
          "with line numbers.", {"path": _s("file name, e.g. main.c"), "start": {"type": "integer"}, "end": {"type": "integer"}},
          ["path"]),
    _tool("apply_patch", "Replace exactly one occurrence of old_text with new_text in main.c.",
          {"path": _s("main.c"), "old_text": _s("exact text to replace"), "new_text": _s("replacement")},
          ["path", "old_text", "new_text"]),
    _tool("rebuild_and_run", "Rebuild the firmware, reboot it in QEMU and run it. "
          "Returns build result, status and UART output.", {}),
    _tool("submit_fix", "Declare the bug fixed. Ends the run; a hidden evaluator then checks behaviour.",
          {"summary": _s("root cause and fix in 1-3 sentences")}, ["summary"]),
]


def dispatch(t, name, a, approve):
    if name == "gdb":
        return t.gdb_command(a["command"])
    if name == "fault_registers":
        return json.dumps(t.fault_registers())
    if name == "read_uart":
        return t.read_uart() or "(empty)"
    if name == "read_source":
        try:
            return t.read_source(a["path"], a.get("start", 1), a.get("end", 200))
        except ValueError as e:
            return f"ERROR: {e}"
    if name == "apply_patch":
        try:
            diff, new_text = t.make_patch(a["path"], a["old_text"], a["new_text"])
        except ValueError as e:
            return f"PATCH REJECTED: {e}"
        if not approve(diff):                       # human-in-the-loop gate
            return "PATCH DENIED by human reviewer"
        t.apply_patch(a["path"], new_text, diff)
        return "PATCH APPLIED:\n" + diff
    if name == "rebuild_and_run":
        return json.dumps(t.rebuild_and_run())
    if name == "submit_fix":
        return "Submitted. Hidden evaluation will run now."
    return f"unknown tool {name}"


def run_agent(t, llm, bug_report, max_steps=20, approve=lambda diff: True,
              trace="trace.jsonl", verbose=True):
    # Observe: boot the target and collect the first evidence for the model
    ok, out = t.build()
    if not ok:
        raise RuntimeError(f"initial build failed: {out}")
    t.start()
    status = t.run()
    obs = (f"BUG REPORT: {bug_report}\n\nINITIAL OBSERVATION\nstatus: {status}\n"
           f"UART: {t.read_uart()!r}\nfault registers: {json.dumps(t.fault_registers())}")
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": obs}]

    log = open(trace, "w")
    outcome, summary, step = "NONE", "", 0
    for step in range(1, max_steps + 1):
        m = llm(messages, TOOLS)
        messages.append({
            "role": "assistant", "content": m["content"],
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                           for c in m["tool_calls"]] or None,
        })
        if not m["tool_calls"]:
            messages.append({"role": "user", "content": "Continue: use a tool, or call submit_fix if done."})
            continue
        for c in m["tool_calls"]:
            result = dispatch(t, c["name"], c["args"], approve)
            log.write(json.dumps({"step": step, "thought": m["content"], "tool": c["name"],
                                  "args": c["args"], "result": result[:2000], "t": time.time()}) + "\n")
            log.flush()
            if verbose:
                print(f"[{step}] {m['content'][:150]}")
                print(f"    -> {c['name']}({json.dumps(c['args'])[:100]})")
                print(f"    <- {result[:200]!r}")
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            if c["name"] == "submit_fix":
                outcome, summary = "SUBMITTED", c["args"].get("summary", "")
                break
        if outcome == "SUBMITTED":
            break
    t.stop()
    log.close()
    return {"outcome": outcome, "steps": step, "summary": summary}
