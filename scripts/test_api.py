"""STEP 1: check that the DeepSeek API works before building anything else.

Test 1: a simple chat message -> print the reply.
Test 2: tool calling with one dummy tool -> check that the model returns a tool call,
        send back a fake tool result, and check that the model gives a final answer.

For each call it prints the model name, token usage and latency.
The API key is read from .env and is NEVER printed.

Run from the project root:
    python scripts/test_api.py
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import APIError, APIStatusError, OpenAI

# Project root = parent of the scripts/ folder, so the script works from any directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Settings that must be present in .env (the key itself is checked but never shown).
REQUIRED_SETTINGS = ["DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "DEEPSEEK_THINKING"]

# One dummy tool for Test 2. The model only has to *ask* for it; we answer with a fake value.
DUMMY_TOOL = {
    "type": "function",
    "function": {
        "name": "get_population",
        "description": "Get the total population of a country for a given year.",
        "parameters": {
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Country name, e.g. Tunisia"},
                "year": {"type": "integer", "description": "Year, e.g. 2020"},
            },
            "required": ["country", "year"],
        },
    },
}


def load_settings() -> dict:
    """Load settings from .env. Exit with a clear message if any is missing."""
    load_dotenv(PROJECT_ROOT / ".env")
    settings = {name: os.getenv(name, "").strip() for name in REQUIRED_SETTINGS}

    missing = [name for name, value in settings.items() if not value]
    if missing:
        sys.exit(f"ERROR: missing in .env: {', '.join(missing)}. See .env.example.")
    if settings["DEEPSEEK_API_KEY"] == "your_key_here":
        sys.exit("ERROR: DEEPSEEK_API_KEY in .env is still the placeholder.")
    if settings["DEEPSEEK_THINKING"] not in ("enabled", "disabled"):
        sys.exit("ERROR: DEEPSEEK_THINKING must be 'enabled' or 'disabled'.")
    return settings


def safe_error_text(error: Exception, api_key: str) -> str:
    """Error message with the API key removed, in case the server echoes it back."""
    return str(error).replace(api_key, "<hidden>")


def call_model(client: OpenAI, settings: dict, messages: list, tools: list | None = None):
    """Send one chat request. Return (message, usage, latency_seconds, model_name)."""
    kwargs = {
        "model": settings["DEEPSEEK_MODEL"],
        "messages": messages,
        # DeepSeek-specific switch for thinking mode (from DeepSeek's docs).
        "extra_body": {"thinking": {"type": settings["DEEPSEEK_THINKING"]}},
    }
    if tools:
        kwargs["tools"] = tools

    start = time.perf_counter()
    response = client.chat.completions.create(**kwargs)
    latency = time.perf_counter() - start
    return response.choices[0].message, response.usage, latency, response.model


def print_stats(model_name: str, usage, latency: float) -> None:
    """Print model name, token usage and latency of one call."""
    print(f"  model:   {model_name}")
    print(
        f"  tokens:  prompt={usage.prompt_tokens}, "
        f"completion={usage.completion_tokens}, total={usage.total_tokens}"
    )
    print(f"  latency: {latency:.2f} s")


def assistant_message_to_dict(message) -> dict:
    """Turn the model's reply into a dict we can send back in the next request.

    In thinking mode DeepSeek requires `reasoning_content` to be sent back during
    tool calls (otherwise: 400 error), so we keep it when it is present.
    """
    as_dict = {"role": "assistant", "content": message.content or ""}
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        as_dict["reasoning_content"] = reasoning
    if message.tool_calls:
        as_dict["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ]
    return as_dict


def test_simple_chat(client: OpenAI, settings: dict) -> bool:
    """Test 1: one simple message. Pass if the reply is not empty."""
    print("\n=== Test 1: simple chat ===")
    messages = [{"role": "user", "content": "Reply with one short sentence: what is the capital of Tunisia?"}]
    message, usage, latency, model_name = call_model(client, settings, messages)
    print(f"  reply:   {message.content!r}")
    print_stats(model_name, usage, latency)

    passed = bool(message.content and message.content.strip())
    print(f"  RESULT:  {'PASS' if passed else 'FAIL (empty reply)'}")
    return passed


def test_tool_call(client: OpenAI, settings: dict) -> bool:
    """Test 2: the model must call the dummy tool, then answer using our fake result."""
    print("\n=== Test 2: tool calling ===")
    messages = [{"role": "user", "content": "What was the population of Tunisia in 2020? Use the tool."}]

    # Round 1: we expect a tool call, not a text answer.
    message, usage, latency, model_name = call_model(client, settings, messages, tools=[DUMMY_TOOL])
    print_stats(model_name, usage, latency)
    if not message.tool_calls:
        print(f"  RESULT:  FAIL (no tool call). Reply was: {message.content!r}")
        return False

    call = message.tool_calls[0]
    print(f"  tool call: name={call.function.name}, arguments={call.function.arguments}")
    try:
        json.loads(call.function.arguments)
    except json.JSONDecodeError as error:
        print(f"  RESULT:  FAIL (arguments are not valid JSON: {error})")
        return False

    # Round 2: send back a FAKE tool result (this is only a connection test, not real data).
    messages.append(assistant_message_to_dict(message))
    for tool_call in message.tool_calls:
        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": "12345678 (test value)"})

    final, usage, latency, model_name = call_model(client, settings, messages, tools=[DUMMY_TOOL])
    print(f"  final reply after tool result: {final.content!r}")
    print_stats(model_name, usage, latency)

    passed = bool(final.content and final.content.strip())
    print(f"  RESULT:  {'PASS' if passed else 'FAIL (no final answer after tool result)'}")
    return passed


def main() -> None:
    """Run both tests and exit with code 0 only if both pass."""
    settings = load_settings()
    print(f"Base URL: {settings['DEEPSEEK_BASE_URL']}")
    print(f"Model (from .env): {settings['DEEPSEEK_MODEL']}  |  thinking: {settings['DEEPSEEK_THINKING']}")
    print("API key: loaded from .env (not shown)")

    client = OpenAI(api_key=settings["DEEPSEEK_API_KEY"], base_url=settings["DEEPSEEK_BASE_URL"])

    results = {}
    for name, test in [("Test 1", test_simple_chat), ("Test 2", test_tool_call)]:
        try:
            results[name] = test(client, settings)
        except APIStatusError as error:
            print(f"  RESULT:  FAIL (HTTP {error.status_code}): {safe_error_text(error, settings['DEEPSEEK_API_KEY'])}")
            results[name] = False
        except APIError as error:
            print(f"  RESULT:  FAIL ({type(error).__name__}): {safe_error_text(error, settings['DEEPSEEK_API_KEY'])}")
            results[name] = False

    print("\n=== Summary ===")
    for name, passed in results.items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
