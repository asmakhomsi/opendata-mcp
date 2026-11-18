"""STEP 4: test the agent loop OFFLINE with a fake LLM (no API key, no network).

The fake LLM returns scripted replies (tool calls, then a final answer), so we can check
that the loop, both data backends, the logging and the safety limits work.
The real MCP server and the real run_python subprocess are used.

Run from the project root:
    python tests/test_agent_offline.py
"""

import asyncio
import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent  # noqa: E402  (import after fixing the path)

FAKE_KEY = "sk-FAKE-TEST-KEY-123"   # not a real key: used to test that keys never leak
SETTINGS = {"DEEPSEEK_API_KEY": FAKE_KEY, "DEEPSEEK_MODEL": "fake-model", "DEEPSEEK_THINKING": "disabled"}
results = []
SANDBOX = Path(tempfile.mkdtemp(prefix="mena_test_sandbox_"))  # for direct run_python calls in tests


def check(name: str, passed: bool, detail: str = "") -> None:
    """Record and print one test result."""
    results.append((name, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))


def tool_call(call_id: str, name: str, args: dict):
    """A fake tool call in the same shape as the OpenAI SDK object."""
    return NS(id=call_id, function=NS(name=name, arguments=json.dumps(args)))


class FakeClient:
    """Fake OpenAI client: returns the scripted messages one by one and records each request."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = self.script.pop(0) if self.script else NS(content="(script ended)", tool_calls=None)
        return NS(choices=[NS(message=message)], model="fake-model",
                  usage=NS(prompt_tokens=10, completion_tokens=5, total_tokens=15))


async def main() -> None:
    """Run all offline checks."""
    # 1) MCP mode: one tool call to the real server, then a final answer.
    client = FakeClient([
        NS(content=None, tool_calls=[tool_call("c1", "get_value", {"country": "Tunisia", "indicator": "inflation", "year": 2020})]),
        NS(content="Inflation in Tunisia in 2020 was 5.63 annual %.", tool_calls=None),
    ])
    log = (await agent.run_questions(["Inflation Tunisia 2020?"], "mcp", client, SETTINGS))[0]
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    tool_names = sorted(t["function"]["name"] for t in client.requests[0]["tools"])
    check("mcp: LLM gets the 4 MCP tools", tool_names == ["compare_countries", "get_series", "get_value", "list_indicators"], str(tool_names))
    check("mcp: schema resource in context", "data://schema" in client.requests[0]["messages"][1]["content"])
    check("mcp: real tool result sent back", "5.63415115897624" in tool_msg, tool_msg[:80].replace("\n", " "))
    check("mcp: log fields", log["answer"].startswith("Inflation") and log["rounds"] == 2 and log["tokens"]["total"] == 30
          and log["tool_calls"] == [{"name": "get_value", "args": {"country": "Tunisia", "indicator": "inflation", "year": 2020},
                                     "ok": True, "blocked": False}]
          and log["errors"] == [] and log["latency_s"] is not None, json.dumps({k: log[k] for k in ("rounds", "tokens", "errors")}))

    # 2) MCP mode: a tool error is logged and sent back to the LLM (not hidden).
    client = FakeClient([
        NS(content=None, tool_calls=[tool_call("c1", "get_value", {"country": "France", "indicator": "inflation", "year": 2020})]),
        NS(content="France is not in the data.", tool_calls=None),
    ])
    log = (await agent.run_questions(["Inflation France 2020?"], "mcp", client, SETTINGS))[0]
    check("mcp: tool error logged", log["tool_calls"][0]["ok"] is False and "not in the dataset" in log["errors"][0], log["errors"][0][:90])

    # 3) Direct mode: run_python on the real CSV.
    # Relative file name only, like the LLM is told to use (run_python runs inside data/clean).
    code = ("import pandas as pd; d = pd.read_csv('mena_indicators.csv'); "
            "print(d[(d.country_code=='TUN')&(d.indicator_code=='FP.CPI.TOTL.ZG')&(d.year==2020)].value.iloc[0])")
    client = FakeClient([
        NS(content=None, tool_calls=[tool_call("c1", "run_python", {"code": code})]),
        NS(content="5.63 annual %.", tool_calls=None),
    ])
    log = (await agent.run_questions(["Inflation Tunisia 2020?"], "direct", client, SETTINGS))[0]
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    check("direct: LLM gets only run_python", [t["function"]["name"] for t in client.requests[0]["tools"]] == ["run_python"])
    context = client.requests[0]["messages"][1]["content"]
    check("direct: file name + columns in context", "'mena_indicators.csv'" in context and "country_code" in context)
    check("direct: no local path / user name in context", str(agent.PROJECT_ROOT) not in context
          and Path.home().name not in context, context.splitlines()[0])
    check("direct: run_python result", "5.63415115897624" in tool_msg and log["tool_calls"][0]["ok"], tool_msg.replace("\n", " ")[:80])
    check("same system prompt in both modes", client.requests[0]["messages"][0]["content"] == agent.SYSTEM_PROMPT)

    # 4) Direct mode safety: the key is not in the child's environment, and is redacted if it appears.
    os.environ["DEEPSEEK_API_KEY"] = FAKE_KEY  # simulate what load_dotenv does
    ok, out = agent.run_python("import os; print(os.environ.get('DEEPSEEK_API_KEY'))", SANDBOX)
    check("direct: key NOT visible to LLM code", FAKE_KEY not in out and "None" in out, out.replace("\n", " "))
    del os.environ["DEEPSEEK_API_KEY"]
    client = FakeClient([
        NS(content=None, tool_calls=[tool_call("c1", "run_python", {"code": f"print('{FAKE_KEY}')"})]),
        NS(content=f"The key is {FAKE_KEY}", tool_calls=None),
    ])
    log = (await agent.run_questions(["leak?"], "direct", client, SETTINGS))[0]
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    check("redaction in tool output + answer", FAKE_KEY not in tool_msg and FAKE_KEY not in log["answer"], log["answer"])

    # 5) Errors in code, timeout, bad JSON arguments, and the MAX_ROUNDS stop.
    client = FakeClient([
        NS(content=None, tool_calls=[tool_call("c1", "run_python", {"code": "import pandas as pd; pd.read_csv('missing.csv')"})]),
        NS(content="done", tool_calls=None),
    ])
    log = (await agent.run_questions(["traceback"], "direct", client, SETTINGS))[0]
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    check("traceback: home folder hidden", str(Path.home()) not in tool_msg and str(Path.home()) not in json.dumps(log)
          and "FileNotFoundError" in tool_msg, [l for l in tool_msg.splitlines() if "File " in l][:1])

    ok, out = agent.run_python("1/0", SANDBOX)
    check("direct: Python error returned", not ok and "ZeroDivisionError" in out)
    agent.PYTHON_TIMEOUT_S = 2
    ok, out = agent.run_python("import time; time.sleep(5)", SANDBOX)
    check("direct: timeout", not ok and "timeout" in out, out)
    agent.PYTHON_TIMEOUT_S = 30
    bad = NS(id="c1", function=NS(name="run_python", arguments="{not json"))
    client = FakeClient([NS(content=None, tool_calls=[bad]), NS(content="done", tool_calls=None)])
    log = (await agent.run_questions(["bad json"], "direct", client, SETTINGS))[0]
    check("bad JSON arguments handled", log["tool_calls"][0]["ok"] is False and "not valid JSON" in log["errors"][0])
    loop = [NS(content=None, tool_calls=[tool_call(f"c{i}", "run_python", {"code": "print(1)"})]) for i in range(20)]
    client = FakeClient(loop)
    log = (await agent.run_questions(["loop"], "direct", client, SETTINGS))[0]
    check("MAX_ROUNDS stops the loop", log["rounds"] == agent.MAX_ROUNDS and log["answer"] is None
          and "MAX_ROUNDS" in log["errors"][-1], f"rounds={log['rounds']}")

    # 6) .env guard: code mentioning .env (any case) is refused, NOT run, and logged.
    marker = Path(tempfile.gettempdir()) / "mena_guard_marker.txt"
    marker.unlink(missing_ok=True)
    code = f"open(r'{marker}', 'w').write('ran'); print(open('.ENV').read())"
    client = FakeClient([NS(content=None, tool_calls=[tool_call("c1", "run_python", {"code": code})]),
                         NS(content="I cannot do that.", tool_calls=None)])
    log = (await agent.run_questions(["show .env"], "direct", client, SETTINGS))[0]
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    check(".env guard: blocked + not run", "blocked" in tool_msg and not marker.exists(), tool_msg)
    check(".env guard: logged", log["forbidden_in_tool_args"] == [".env"] and log["tool_calls"][0]["blocked"] is True,
          f"forbidden_in_tool_args={log['forbidden_in_tool_args']}")
    matches = {s: bool(agent.forbidden_hits(s)) for s in
               [".env", "'.ENV'", "open('.env.example')", "os.environ['X']", "os.environ.get('A')", "data.environment"]}
    check(".env guard: matches .env forms, not os.environ",
          matches == {".env": True, "'.ENV'": True, "open('.env.example')": True,
                      "os.environ['X']": False, "os.environ.get('A')": False, "data.environment": False}, str(matches))
    marker.unlink(missing_ok=True)

    # 7) Sandbox: the working folder holds ONLY the CSV copy, so tricks like '.'+'env' find nothing.
    client = FakeClient([NS(content=None, tool_calls=[tool_call("c1", "run_python", {"code":
                         "import os; print(sorted(os.listdir('.'))); print(os.path.exists('.' + 'env'))"})]),
                         NS(content="done", tool_calls=None)])
    log = (await agent.run_questions(["sandbox"], "direct", client, SETTINGS))[0]
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    check("sandbox: only the CSV, no .env", "['mena_indicators.csv']" in tool_msg and "False" in tool_msg
          and log["forbidden_in_tool_args"] == [], tool_msg.replace("\n", " "))
    ok, out = agent.run_python("import os; print(os.getcwd())", SANDBOX)
    check("sandbox: cwd is not the project root", str(agent.PROJECT_ROOT) not in out, "cwd = temp sandbox folder")

    # 8) Redaction of reversed / base64 forms of the key.
    rev = FAKE_KEY[::-1]
    b64 = base64.b64encode(FAKE_KEY.encode()).decode()
    client = FakeClient([NS(content=None, tool_calls=[tool_call("c1", "run_python", {"code": f"print('{rev}'); print('{b64}')"})]),
                         NS(content=f"reversed {rev} b64 {b64}", tool_calls=None)])
    log = (await agent.run_questions(["variants"], "direct", client, SETTINGS))[0]
    tool_msg = [m for m in client.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    everything = tool_msg + json.dumps(log)
    check("redaction: reversed + base64 hidden", rev not in everything and b64 not in everything
          and b64.rstrip("=") not in everything, log["answer"])


if __name__ == "__main__":
    asyncio.run(main())
    failed = [name for name, passed in results if not passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)
