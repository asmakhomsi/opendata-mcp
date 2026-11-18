"""STEP 6: run every test question in one mode and save the raw results.

Uses the DeepSeek API key (from .env), so it is run by the user, not by Claude.
Same model, same system prompt, same questions in both modes: only data access changes.

Output: results/results_<mode>.jsonl  (one JSON record per question, written as soon as it
is answered, so a crash keeps the answers already done).

Run from the project root:
    python eval/run_eval.py --mode mcp
    python eval/run_eval.py --mode direct
Then grade (no API key needed):
    python eval/summarize.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import agent  # noqa: E402  (import after fixing the path)

TESTSET_FILE = PROJECT_ROOT / "tests" / "testset.json"
RESULTS_DIR = PROJECT_ROOT / "results"


def main() -> None:
    """Run all questions in the chosen mode and write one JSON line per question."""
    parser = argparse.ArgumentParser(description="Run the test set in one mode.")
    parser.add_argument("--mode", required=True, choices=["mcp", "direct"])
    cli = parser.parse_args()

    testset = json.loads(TESTSET_FILE.read_text(encoding="utf-8"))
    settings = agent.load_settings()
    client = OpenAI(api_key=settings["DEEPSEEK_API_KEY"], base_url=settings["DEEPSEEK_BASE_URL"])

    RESULTS_DIR.mkdir(exist_ok=True)
    out_file = RESULTS_DIR / f"results_{cli.mode}.jsonl"
    print(f"Mode: {cli.mode} | model: {settings['DEEPSEEK_MODEL']} | {len(testset)} questions -> "
          f"results/{out_file.name}")

    with open(out_file, "w", encoding="utf-8") as f:

        def save(index: int, log: dict) -> None:
            """Write one record (id + category + the agent log) right away and show progress.

            The test's check spec is NOT copied here (it contains strings like the key prefix
            that the secret scanner looks for).
            """
            item = testset[index]
            record = {"id": item["id"], "category": item["category"], "language": item["language"], **log}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            status = "ERR" if any(not e.startswith("tool ") for e in log["errors"]) else "ok "
            print(f"[{index + 1:2d}/{len(testset)}] {status} {item['id']}  tools={len(log['tool_calls'])} "
                  f"tokens={log['tokens']['total']:5d}  {log['latency_s']:6.2f}s")

        try:
            asyncio.run(agent.run_questions([q["question"] for q in testset], cli.mode, client, settings, save))
        except Exception as error:  # report a crash clearly; the answers already saved are kept
            print(f"\nRUN CRASHED: {type(error).__name__}: {agent.redact(str(error), settings['DEEPSEEK_API_KEY'])}")
            print(f"Answers saved so far are in results/{out_file.name}.")
            sys.exit(1)

    print(f"\nDone. Saved results/{out_file.name}. Next: python eval/summarize.py")


if __name__ == "__main__":
    main()
