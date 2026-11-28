"""One interface to any LLM.

Every LLM callable takes (messages, tools) and returns
    {"content": str, "tool_calls": [{"id": str, "name": str, "args": dict}]}

Switch models with the MODEL env var, for example:
    gemini/gemini-2.5-flash   (needs GEMINI_API_KEY)
    ollama/qwen2.5-coder:7b   (local, free)
"""
import json
import os


def litellm_chat(messages, tools):
    import litellm

    litellm.drop_params = True   # ignore settings a model doesn't support
    r = litellm.completion(
        model=os.environ["MODEL"], messages=messages, tools=tools, num_retries=6,
    )
    m = r.choices[0].message
    calls = [
        {"id": c.id, "name": c.function.name, "args": json.loads(c.function.arguments or "{}")}
        for c in (m.tool_calls or [])
    ]
    return {"content": m.content or "", "tool_calls": calls}


class ScriptedLLM:
    """Offline stand-in used to test the plumbing: replays a fixed list of (tool, args)."""

    def __init__(self, script):
        self.script = list(script)
        self.n = 0

    def __call__(self, messages, tools):
        name, args = self.script.pop(0)
        self.n += 1
        return {
            "content": f"(scripted step {self.n})",
            "tool_calls": [{"id": f"c{self.n}", "name": name, "args": args}],
        }
