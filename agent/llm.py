"""Gemini access through LiteLLM.

litellm_chat(messages, tools) returns
    {"content": str, "tool_calls": [{"id": str, "name": str, "args": dict}]}

Configured by environment variables (or .env):
    MODEL=gemini/gemini-2.5-flash
    GEMINI_API_KEY=...
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
