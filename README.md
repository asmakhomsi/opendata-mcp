# Open Data through MCP: MENA indicators

An LLM agent (DeepSeek) answers questions about MENA open data: 5 countries (Algeria, Egypt, Jordan,
Morocco, Tunisia), 5 World Bank indicators, 2010–2025. It reaches **the same data in two ways**:

| Mode | Data access |
|---|---|
| `mcp` | our MCP server (`server.py`, FastMCP over stdio): 4 curated tools + the `data://schema` resource |
| `direct` | the CSV file + one `run_python` tool (the LLM writes its own pandas code, run in a sandbox folder) |

Same LLM, same model, same system prompt and same 33 test questions in both modes; only data access changes.
Results and the decision are in [docs/analysis.md](docs/analysis.md).

## Data source and licence
World Bank, World Development Indicators (bulk CSV download, last updated 2026-11-11).
Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Cite as "World Bank, World Development Indicators".

| Indicator code | Name | Unit |
|---|---|---|
| SL.UEM.TOTL.ZS | Unemployment, total (modeled ILO estimate) | % of total labor force |
| SL.UEM.1524.ZS | Unemployment, youth total, ages 15-24 (modeled ILO estimate) | % of total labor force ages 15-24 |
| NY.GDP.MKTP.KD.ZG | GDP growth | annual % |
| FP.CPI.TOTL.ZG | Inflation, consumer prices | annual % |
| SP.POP.TOTL | Population, total | people |

The data is stored locally in `data/` (the agent never calls the World Bank API). 400 rows, no missing values.
Unemployment values for 2024–2025 are ILO modeled estimates.

## Requirements
- Python **3.10 or newer** (needed by the MCP SDK). Developed and tested with **Python 3.13.5** on Windows.
- A DeepSeek API key.
- Optional: Node.js (only for the MCP Inspector).

## Setup

**Windows (PowerShell)**
```powershell
python -m venv .venv                 # 1. create the virtual environment
.venv\Scripts\Activate.ps1           # 2. activate it
pip install -r requirements.txt      # 3. install the pinned dependencies
Copy-Item .env.example .env          # 4. create .env, then put your DeepSeek key in it
Copy-Item scripts\pre-commit .git\hooks\pre-commit   # 5. (optional) secret check before each commit
```

**Mac / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

Settings in `.env` (see `.env.example`): `DEEPSEEK_API_KEY` (secret, never commit it), `DEEPSEEK_BASE_URL`
(`https://api.deepseek.com`), `DEEPSEEK_MODEL` (`deepseek-flash`), `DEEPSEEK_THINKING` (`disabled`), `MODE` (`mcp` or `direct`).

The MCP SDK is pinned below 2.0 (`mcp==1.30.0`) because we use the classic
`from mcp.server.fastmcp import FastMCP` API.

## How to run

```powershell
python scripts/test_api.py                     # 1. check the DeepSeek key (chat + tool calling)
python scripts/build_dataset.py                # 2. rebuild data/clean/mena_indicators.csv from data/raw/
python agent.py --mode mcp    "What was youth unemployment in Tunisia in 2023?"
python agent.py --mode direct "What was youth unemployment in Tunisia in 2023?"
```
`agent.py` prints the answer and a JSON log (tool calls, tokens, latency, errors). Without `--mode`, it uses `MODE` from `.env`.
Add `--log results/demo_log.jsonl` to save the log.

**MCP server alone** (to inspect the tools):
```powershell
npx @modelcontextprotocol/inspector python server.py
```

## Evaluation

```powershell
python tests/make_testset.py              # build tests/testset.json (33 questions, expected answers computed from the CSV)
python eval/run_eval.py --mode mcp        # uses the API key -> results/results_mcp.jsonl
python eval/run_eval.py --mode direct     # uses the API key -> results/results_direct.jsonl
python eval/summarize.py                  # no key: grading -> results/summary.md, summary.csv, graded_*.jsonl
python scripts/check_secrets.py           # scan results/ for the key before committing
python scripts/show_saved.py CMP05        # show a saved answer in both modes (offline)
```
Grading is rule-based; uncertain answers are flagged `needs_manual_review` and decided by a human in
`results/manual_review.json` (listed in `results/manual_review.md`). Hypotheses were written first in
[docs/hypotheses.md](docs/hypotheses.md).

## Tests (no API key needed)

```powershell
python tests/test_server.py          # MCP tools + resource over the real stdio protocol (15 checks)
python tests/test_agent_offline.py   # agent loop with a fake LLM, both modes, safety layers (23 checks)
python tests/test_summarize.py       # grading rules on hand-written answers (40 checks)
```

## Safety
- The API key lives only in `.env` (git-ignored) and is never printed or logged.
- `run_python` (direct mode): code that mentions `.env` is refused and logged; code runs in a temporary folder
  holding only a copy of the CSV; DeepSeek variables are removed from its environment; the key (plain, reversed,
  base64) and the home folder path are redacted from every output. This is **not** full OS isolation.
- `scripts/check_secrets.py` (and the pre-commit hook) blocks a commit if `results/` contains the key.

## Project layout
```
server.py                 MCP server (4 tools + data://schema)
agent.py                  agent: one loop, one system prompt, MODE=mcp | direct
scripts/                  test_api.py, build_dataset.py, check_secrets.py, show_saved.py, pre-commit
data/raw/                 the 5 World Bank CSV files (unchanged)
data/clean/               mena_indicators.csv (tidy, 400 rows)
tests/                    make_testset.py, testset.json, test_server.py, test_agent_offline.py, test_summarize.py
eval/                     run_eval.py, summarize.py
results/                  raw results, graded results, summary, manual review
docs/                     hypotheses.md, analysis.md
```
