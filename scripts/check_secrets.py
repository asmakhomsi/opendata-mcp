"""Safety check before committing: scan results/ for the DeepSeek API key.

It looks for:
  - the text "sk-" (DeepSeek keys start with it);
  - the real key from .env in plain, reversed and base64 forms (standard and URL-safe,
    with and without "=" padding, also base64 of the reversed key).

The key is read from .env but NEVER printed: findings show only the file, the line number
and which form was found. Exit code 1 if anything is found (this blocks the git commit
when used as a pre-commit hook), 0 if results/ is clean.

Run from the project root:
    python scripts/check_secrets.py
Options (used by the tests, with a fake key):
    --env-file PATH   read the key from another file
    --dir PATH        scan another folder
"""

import argparse
import base64
import sys
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def key_forms(key: str) -> dict[str, str]:
    """All the forms of the key we search for, with a label for each (labels are safe to print)."""
    raw = key.encode("utf-8")
    forms = {"plain key": key, "reversed key": key[::-1]}
    encodings = {
        "base64 key": base64.b64encode(raw),
        "base64 (url-safe) key": base64.urlsafe_b64encode(raw),
        "base64 of reversed key": base64.b64encode(raw[::-1]),
        "base64 (url-safe) of reversed key": base64.urlsafe_b64encode(raw[::-1]),
    }
    for label, encoded in encodings.items():
        text = encoded.decode("ascii")
        forms[label] = text
        forms[label + " (no padding)"] = text.rstrip("=")
    return forms


def scan_file(path: Path, patterns: dict[str, str]) -> list[str]:
    """Return findings "file:line: label" for one file (never the matched text)."""
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return [f"{path}: could not read ({error.strerror})"]
    for line_no, line in enumerate(text.splitlines(), start=1):
        for label, pattern in patterns.items():
            if pattern and pattern in line:
                findings.append(f"{path}:{line_no}: found {label}")
    return findings


def main() -> None:
    """Scan the folder and exit 1 if any secret-looking text is found."""
    parser = argparse.ArgumentParser(description="Scan results/ for the DeepSeek API key.")
    parser.add_argument("--env-file", default=str(PROJECT_ROOT / ".env"))
    parser.add_argument("--dir", default=str(PROJECT_ROOT / "results"))
    cli = parser.parse_args()

    patterns = {"'sk-' (key prefix)": "sk-"}
    key = (dotenv_values(cli.env_file).get("DEEPSEEK_API_KEY") or "").strip()
    if key and key != "your_key_here":
        patterns.update(key_forms(key))
    else:
        print("WARNING: no real DEEPSEEK_API_KEY found in the env file; only checking for 'sk-'.")

    folder = Path(cli.dir)
    if not folder.is_dir():
        sys.exit(f"ERROR: folder not found: {folder}")
    files = sorted(p for p in folder.rglob("*") if p.is_file())

    findings = [f for path in files for f in scan_file(path, patterns)]
    if findings:
        print(f"SECRET CHECK FAILED: {len(findings)} finding(s) in {folder}. Do NOT commit.")
        for finding in findings:
            print("  " + finding)
        print("Open the file(s), remove the line(s), then run this check again.")
        sys.exit(1)
    print(f"Secret check OK: {len(files)} file(s) in {folder} scanned, no key found "
          f"({len(patterns)} patterns checked).")


if __name__ == "__main__":
    main()
