"""Show a SAVED answer from the evaluation, offline (no API key, no internet).

It prints what the agent really answered during the evaluation run (results/), with its
tool calls, tokens, latency and the graded verdict.

Run from the project root:
    python scripts/show_saved.py LKP01            # both modes, side by side
    python scripts/show_saved.py CMP05 --mode mcp # one mode only
    python scripts/show_saved.py --list           # all question ids
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"


def load(kind: str, mode: str) -> dict:
    """Load results/<kind>_<mode>.jsonl as {question id: record}."""
    path = RESULTS_DIR / f"{kind}_{mode}.jsonl"
    if not path.exists():
        sys.exit(f"ERROR: {path.name} not found. Run the evaluation first (eval/run_eval.py).")
    return {json.loads(line)["id"]: json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def show(question_id: str, mode: str) -> None:
    """Print one saved record."""
    record = load("results", mode).get(question_id)
    if record is None:
        sys.exit(f"ERROR: no question '{question_id}'. Use --list to see the ids.")
    graded = load("graded", mode)[question_id]
    print(f"\n=== {mode.upper()} | {question_id} ({record['category']}) ===")
    print(f"Question: {record['question']}")
    for call in record["tool_calls"]:
        args = call["args"]
        text = args.get("code", "") if isinstance(args, dict) and "code" in args else json.dumps(args, ensure_ascii=False)
        print(f"  tool: {call['name']}  {text.strip()[:300]}")
    print(f"Answer: {record['answer']}")
    print(f"tokens={record['tokens']['total']}  latency={record['latency_s']} s  rounds={record['rounds']}  "
          f"verdict={graded['final_verdict']}")


def main() -> None:
    """Parse arguments and show the saved answer(s)."""
    parser = argparse.ArgumentParser(description="Show saved evaluation answers (offline).")
    parser.add_argument("question_id", nargs="?", help="e.g. LKP01, CMP05, INJ01")
    parser.add_argument("--mode", choices=["mcp", "direct"], help="default: both")
    parser.add_argument("--list", action="store_true", help="list all question ids")
    cli = parser.parse_args()

    if cli.list or not cli.question_id:
        for qid, record in load("results", "mcp").items():
            print(f"{qid}  [{record['category']}]  {record['question']}")
        return
    for mode in [cli.mode] if cli.mode else ["mcp", "direct"]:
        show(cli.question_id.upper(), mode)


if __name__ == "__main__":
    main()
