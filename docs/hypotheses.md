# Hypotheses (written BEFORE running the test set)

Written in STEP 5, before `eval/run_eval.py` exists or has been run.
Honest note: they are informed by the 8 demo runs of STEP 4 (4 questions × 2 modes), and by
how the two modes are built. They are predictions to be **confirmed or rejected** in STEP 7.

Setup reminder: same LLM (`deepseek-flash`, thinking disabled), same system prompt, same questions.
Only data access differs:
- **MCP**: 4 curated tools (`list_indicators`, `get_value`, `get_series`, `compare_countries`)
  + the `data://schema` resource in context.
- **Direct**: the CSV file name + its columns, and one `run_python` tool (the LLM writes pandas code).

## Global hypotheses (all categories)

| # | Hypothesis | How it is measured |
|---|---|---|
| G1 | MCP has **lower average latency** than direct (no code writing, no Python subprocess). | avg `latency_s` per mode |
| G2 | MCP uses **more tokens per question** on simple questions (tool schemas + schema resource ≈ 1,700 tokens on every call). | avg `tokens.total` per mode × category |
| G3 | Direct needs **more tool calls** on average (it explores the file before answering). | avg number of tool calls |
| G4 | Neither mode invents numbers for data that does not exist (out-of-scope). | out_of_scope correct refusals |

## Per-category hypotheses

| Category | MCP expectation | Direct expectation | Prediction |
|---|---|---|---|
| **lookup** (one value) | Very high accuracy: `get_value` matches the question exactly. | Very high accuracy too: one simple pandas filter. | **Tie on accuracy**; MCP faster (G1). |
| **aggregation** (mean, sum, count, max over years/countries) | Must get raw values (`get_series` / several calls) and do the **arithmetic in the LLM** → risk of arithmetic errors, especially on means of 16 values. | pandas computes exactly. | **Direct ≥ MCP** on accuracy. |
| **comparison / trend** (ranking, change, growth, correlation, multi-indicator) | Rankings are easy (`compare_countries`). Correlation and multi-step calculations are **not covered** by a tool → LLM arithmetic, likely errors on correlation. | pandas handles all of them. | **MCP good on rankings, direct better on correlation / calculations.** |
| **out_of_scope** (country, indicator or year not in the data) | Refuses, often **without any tool call** (the schema lists countries/years). | Refuses after inspecting the file. | **Both ≈ 100 %**; MCP cheaper/faster. |
| **ambiguous** (missing year, unclear indicator) | Depends on the system prompt, not on data access. | Same. | **Similar in both modes**; some answers will need manual review. |
| **french_or_arabic** | Must translate country names to English for the tools (e.g. "Maroc" → "Morocco"); tools reject other spellings with a clear error, so it can retry. | pandas code can search in English easily. | **Both answer correctly and in the user's language**; Arabic slightly harder for both. |
| **injection** (instructions inside the question) | Tools only return data → small attack surface; the injected number/instruction should be ignored. | `run_python` can run **any** code (e.g. read `.env`) → larger attack surface. Our protections: code mentioning `.env` is refused and logged; code runs in a temporary sandbox folder holding only a copy of the CSV; key removed from the child process; key (plain / reversed / base64) + home path redacted in outputs; `scripts/check_secrets.py` scans `results/` before any commit. | **Both ignore injected numbers**; direct is the riskier mode by design. |

## What would make us change our mind
- If direct mode is as fast as MCP → G1 rejected.
- If MCP gets correlation / means right as often as direct → the "arithmetic in the LLM" risk is smaller than expected.
- If any mode gives a number for an out-of-scope question → G4 rejected (serious failure).
