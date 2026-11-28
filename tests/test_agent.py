"""Stage 3 tests: analysis, agent loop (with a scripted LLM, no API calls), RAG chunking."""
import json
import os
import shutil

import pytest

from agent.agent import TOOLS, Agent
from agent.analysis import analyze, compare_uart, format_report
from rag.ingestion import chunk, doc_info
from tools.target import Target

needs_qemu = pytest.mark.skipif(
    not all(shutil.which(x) for x in ("qemu-system-arm", "arm-none-eabi-gcc", "gdb-multiarch")),
    reason="embedded toolchain not installed")
EXPECTED = ["boot ok", "rx ok", "init done"]


class FakeLLM:
    """Replays a fixed list of (tool, args) calls, recording what it was shown."""

    def __init__(self, script):
        self.script, self.seen = list(script), []

    def __call__(self, messages, tools):
        self.seen.append(messages[-1]["content"])
        name, args = self.script.pop(0)
        n = len(self.seen)
        return {"content": f"step {n}", "tool_calls": [{"id": f"c{n}", "name": name, "args": args}]}


# ---------- offline ----------
def test_compare_uart():
    c = compare_uart("boot ok\n", EXPECTED)
    assert not c["ok"] and c["missing"] == ["rx ok", "init done"] and c["last_line"] == "boot ok"
    assert compare_uart("boot ok\nrx ok\ninit done\n", EXPECTED)["ok"]
    assert compare_uart("rx ok\nboot ok\ninit done\n", EXPECTED)["missing"] == ["rx ok", "init done"]


def test_tools_match_spec():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"read_source", "build_firmware", "run_firmware", "read_uart", "gdb_command",
                     "fault_registers", "retrieve_docs", "apply_patch", "verify_fix"}


def test_chunking_overlaps_and_bounds():
    text = " ".join(f"word{i}" for i in range(1000))
    parts = chunk(text, size=300, overlap=60)
    assert len(parts) > 10 and all(len(p) <= 300 for p in parts)
    assert parts[0].split()[-1] in parts[1]                    # overlap carries context


def test_clean_joins_layout_lines():
    from rag.ingestion import clean
    assert clean("Bit 1\nUDIS: Update disable\n\nNext para") == "Bit 1 UDIS: Update disable\n\nNext para"


needs_index = pytest.mark.skipif(not os.path.isdir("knowledge_base/chroma"),
                                 reason="RAG index not built (python -m rag.ingestion)")


@needs_index
@pytest.mark.parametrize("query,source", [
    ("BusFault PRECISERR BFAR imprecise", "Cortex-M3"),
    ("TIM2 CR1 counter enable CEN UDIS", "RM0033"),
    ("SysTick exception handler vector table", "Cortex-M3"),
])
def test_retriever_finds_relevant_manual(query, source):
    from rag.retriever import Retriever
    hits = Retriever(k=3)(query)
    assert hits and all(h["page"] > 0 for h in hits)
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    assert any(source in h["source"] or source in h["file"] for h in hits)


def test_doc_info_maps_known_manuals():
    assert doc_info("x/rm0033-stm32-armbased-32bit.pdf")[0].startswith("RM0033")
    assert doc_info("DUI0552A_cortex_m3_dgug.pdf")[1] is None  # indexed in full


# ---------- QEMU ----------
@needs_qemu
def test_analysis_reports_fault_and_source(tmp_path):
    t = Target("fw/bug_001", str(tmp_path / "ws"))
    try:
        r = analyze(t, EXPECTED)
    finally:
        t.stop()
    assert r["status"] == "HARDFAULT" and r["uart_check"]["missing"] == ["rx ok", "init done"]
    assert any("on_rx" in w for w in r["warnings"])            # compiler hint is kept
    assert any("> 15:" in c["code"] and "rx_callback();" in c["code"] for c in r["context"])
    text = format_report(r, EXPECTED)
    assert "INVSTATE" in text and "SOURCE AROUND main.c:15" in text


@needs_qemu
def test_analysis_locates_hang(tmp_path):
    t = Target("fw/bug_009", str(tmp_path / "ws"))
    try:
        r = analyze(t, ["boot ok", "batches 3", "init done"], seconds=2)
    finally:
        t.stop()
    assert r["status"] == "NO_FAULT" and "main.c" in (r["halted_at"] or "")


@needs_qemu
def test_agent_loop_fixes_bug_with_scripted_llm(tmp_path):
    llm = FakeLLM([
        ("gdb_command", {"command": "shell id"}),                      # must be rejected
        ("retrieve_docs", {"query": "INVSTATE"}),
        ("apply_patch", {"path": "main.c", "old_text": "  rx_callback();",
                         "new_text": "  rx_callback = on_rx;\n  rx_callback();",
                         "root_cause": "rx_callback is NULL when called"}),
        ("verify_fix", {}),
    ])
    t = Target("fw/bug_001", str(tmp_path / "ws"))
    agent = Agent(t, llm, "stops after boot ok", EXPECTED, retriever=None,
                  trace=str(tmp_path / "trace.jsonl"), verbose=False)
    res = agent.run()
    assert res["outcome"] == "FIXED" and res["fix_attempts"] == 1 and res["steps"] == 4
    assert res["root_cause"] == "rx_callback is NULL when called"
    assert "rx_callback = on_rx" in res["patch"]
    assert "SOURCE main.c" in llm.seen[0] and "HARDFAULT" in llm.seen[0]  # observation content
    assert llm.seen[1].startswith("REJECTED")                            # sandboxed gdb
    trace = [json.loads(l) for l in open(tmp_path / "trace.jsonl")]
    assert trace[0]["tool"] == "analyze" and trace[-1]["tool"] == "verify_fix"


@needs_qemu
def test_agent_stops_at_attempt_limit(tmp_path):
    bad = ("apply_patch", {"path": "main.c", "old_text": '  uart_puts("init done\\n");',
                           "new_text": '  uart_puts("init  done\\n");', "root_cause": "x"})
    llm = FakeLLM([bad, ("verify_fix", {})])
    t = Target("fw/bug_001", str(tmp_path / "ws"))
    res = Agent(t, llm, "bug", EXPECTED, max_attempts=1, trace=str(tmp_path / "t.jsonl"),
                verbose=False).run()
    assert res["outcome"] == "ATTEMPT_LIMIT" and res["fix_attempts"] == 1


@needs_qemu
def test_denied_patch_is_not_applied(tmp_path):
    llm = FakeLLM([("apply_patch", {"path": "main.c", "old_text": "  rx_callback();",
                                    "new_text": "", "root_cause": "x"})])
    t = Target("fw/bug_001", str(tmp_path / "ws"))
    res = Agent(t, llm, "bug", EXPECTED, approve=lambda d: False, max_steps=1,
                trace=str(tmp_path / "t.jsonl"), verbose=False).run()
    assert res["outcome"] == "STEP_LIMIT" and res["patch"] == ""
