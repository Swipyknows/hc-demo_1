"""The debugging agent: one LLM (Gemini via LiteLLM) with a fixed set of tools.

Loop: Observe -> Analyze -> Debug -> Fix -> Verify, until verify_fix passes, the fix
attempt limit is reached, or the step limit is reached.
"""
import json
import time

from agent.analysis import analyze, compare_uart, format_report
from agent.prompts import NUDGE, SYSTEM, initial_observation
from tools.target import NO_FAULT


def _tool(name, desc, props=None, required=()):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": list(required)}}}


def _s(desc):
    return {"type": "string", "description": desc}


TOOLS = [
    _tool("read_source", "Read a firmware source file with line numbers "
          "(main.c, startup.c, board.h, link.ld).",
          {"path": _s("file name, e.g. main.c"), "start": {"type": "integer"},
           "end": {"type": "integer"}}, ["path"]),
    _tool("build_firmware", "Compile the current firmware with ARM GCC; returns errors/warnings."),
    _tool("run_firmware", "Rebuild, boot in QEMU, run, and return the analysed evidence report "
          "(status, UART vs expected, fault, backtrace, source context). CPU is halted after."),
    _tool("read_uart", "Return everything the firmware printed on the serial console."),
    _tool("gdb_command", "Run one GDB command on the halted target, e.g. 'bt', 'info registers', "
          "'x/8wx $sp', 'p ticks', 'info symbol 0x8000100', 'x/1wx 0x40000000'.",
          {"command": _s("GDB command")}, ["command"]),
    _tool("fault_registers", "Decoded Cortex-M fault status (CFSR/HFSR/MMFAR/BFAR), the active "
          "exception and the stacked exception frame with faulting source line."),
    _tool("retrieve_docs", "Search the ARM Cortex-M / STM32 documentation knowledge base.",
          {"query": _s("what to look up, e.g. 'CFSR INVSTATE bit meaning'")}, ["query"]),
    _tool("apply_patch", "Replace exactly one occurrence of old_text with new_text in main.c. "
          "Shown to a human for approval.",
          {"path": _s("main.c"), "old_text": _s("exact existing text"),
           "new_text": _s("replacement text"),
           "root_cause": _s("the root cause this patch fixes, 1-2 sentences")},
          ["path", "old_text", "new_text", "root_cause"]),
    _tool("verify_fix", "Rebuild and run the patched firmware and check it against the expected "
          "output. Ends the session when it passes."),
]


class Agent:
    def __init__(self, t, llm, bug_report, expected, approve=lambda diff: True,
                 retriever=None, max_steps=25, max_attempts=3, trace="trace.jsonl",
                 verbose=True):
        self.t, self.llm, self.bug, self.expected = t, llm, bug_report, expected
        self.approve, self.retriever = approve, retriever
        self.max_steps, self.max_attempts = max_steps, max_attempts
        self.trace_path, self.verbose = trace, verbose
        self.attempts, self.root_cause, self.rag_queries = 0, "", []
        self.outcome = "NOT_FIXED"

    # ---------- tool dispatch ----------
    def dispatch(self, name, a):
        t = self.t
        if name == "read_source":
            try:
                return t.read_source(a.get("path", "main.c"), a.get("start", 1), a.get("end", 400))
            except ValueError as e:
                return f"ERROR: {e}"
        if name == "build_firmware":
            ok, out = t.build()
            return ("BUILD OK" if ok else "BUILD FAILED") + (f"\n{out}" if out else "")
        if name == "run_firmware":
            return format_report(analyze(t, self.expected), self.expected)
        if name == "read_uart":
            return t.read_uart() or "(empty)"
        if name == "gdb_command":
            return t.gdb_command(a.get("command", ""))
        if name == "fault_registers":
            return json.dumps(t.fault_registers(), indent=1) if t.gdb else "target not running"
        if name == "retrieve_docs":
            return self._retrieve(a.get("query", ""))
        if name == "apply_patch":
            return self._apply_patch(a)
        if name == "verify_fix":
            return self._verify()
        return f"ERROR: unknown tool {name}"

    def _retrieve(self, query):
        if self.retriever is None:
            return "Documentation retrieval is not available in this configuration."
        hits = self.retriever(query)
        self.rag_queries.append({"query": query,
                                 "hits": [{"source": h["source"], "page": h["page"],
                                           "score": h["score"]} for h in hits]})
        if not hits:
            return "No relevant documentation found."
        return "\n\n".join(f"[{h['source']} p.{h['page']}]\n{h['text']}" for h in hits)

    def _apply_patch(self, a):
        try:
            diff, new_text = self.t.make_patch(a.get("path", "main.c"), a.get("old_text", ""),
                                               a.get("new_text", ""))
        except ValueError as e:
            return f"PATCH REJECTED: {e}"
        if not self.approve(diff):
            return "PATCH DENIED by the human reviewer. Propose a different fix."
        self.t.apply_patch(a.get("path", "main.c"), new_text, diff)
        self.root_cause = a.get("root_cause", self.root_cause)
        return "PATCH APPLIED:\n" + diff + "\nNow call verify_fix."

    def _verify(self):
        if not self.t.patches:
            return "No patch has been applied yet. Use apply_patch first."
        self.attempts += 1
        r = analyze(self.t, self.expected)
        passed = (r["build"] == "OK" and r["status"] == NO_FAULT
                  and compare_uart(r["uart"], self.expected)["ok"])
        if passed:
            self.outcome = "FIXED"
            return "VERIFY: PASS\n" + format_report(r, self.expected)
        left = self.max_attempts - self.attempts
        return (f"VERIFY: FAIL (attempt {self.attempts}/{self.max_attempts}, {left} left)\n"
                + format_report(r, self.expected))

    # ---------- main loop ----------
    def run(self):
        t0, log = time.time(), open(self.trace_path, "w")

        def record(step, thought, tool, args, result):
            log.write(json.dumps({"step": step, "thought": thought, "tool": tool, "args": args,
                                  "result": result[:3000], "t": round(time.time() - t0, 2)}) + "\n")
            log.flush()
            if self.verbose:
                print(f"[{step}] {thought[:200]}" if thought else f"[{step}]")
                print(f"    -> {tool}({json.dumps(args)[:160]})")
                print(f"    <- {result[:300]!r}")

        # Observe: read source, build, run, analyse (automatic, before the first LLM call)
        source = self.t.read_source("main.c", 1, 400)
        evidence = analyze(self.t, self.expected)
        report = format_report(evidence, self.expected)
        record(0, "initial observation", "analyze", {}, report)
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": initial_observation(
                        self.bug, self.expected, source, report)}]

        step = 0
        try:
            for step in range(1, self.max_steps + 1):
                m = self.llm(messages, TOOLS)
                messages.append({"role": "assistant", "content": m["content"] or None,
                                 "tool_calls": [{"id": c["id"], "type": "function",
                                                 "function": {"name": c["name"],
                                                              "arguments": json.dumps(c["args"])}}
                                                for c in m["tool_calls"]] or None})
                if not m["tool_calls"]:
                    record(step, m["content"], "(none)", {}, "")
                    messages.append({"role": "user", "content": NUDGE})
                    continue
                for c in m["tool_calls"]:
                    result = self.dispatch(c["name"], c["args"])
                    record(step, m["content"], c["name"], c["args"], result)
                    messages.append({"role": "tool", "tool_call_id": c["id"],
                                     "name": c["name"], "content": result})
                if self.outcome == "FIXED" or self.attempts >= self.max_attempts:
                    break
        finally:
            self.t.stop()
            log.close()
        outcome = self.outcome
        if outcome != "FIXED":
            outcome = "ATTEMPT_LIMIT" if self.attempts >= self.max_attempts else "STEP_LIMIT"
        return {"outcome": outcome,
                "steps": step, "fix_attempts": self.attempts, "root_cause": self.root_cause,
                "patch": self.t.total_diff(), "rag_queries": self.rag_queries,
                "initial_evidence": {k: v for k, v in evidence.items() if k != "context"},
                "seconds": round(time.time() - t0, 1)}


def run_agent(t, llm, bug_report, expected, **kw):
    return Agent(t, llm, bug_report, expected, **kw).run()
