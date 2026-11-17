# Open Data through MCP: MENA indicators

An LLM agent (DeepSeek) answers questions about MENA open data (5 countries, 5 World Bank
indicators, 2010–2025). It reaches the data either through our own MCP server (`MODE=mcp`) or
through the raw CSV and a `run_python` tool (`MODE=direct`). Both modes are then compared on the same test set.

## Data source and licence
World Bank, World Development Indicators (bulk CSV download, last updated 2026-11-11).
Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Countries: Tunisia, Morocco, Algeria, Egypt, Jordan. Years: 2010–2025.

## Requirements
- Python **3.10 or newer** (needed by the MCP SDK). Developed and tested with **Python 3.13.5**.

## Setup

**Windows (PowerShell)**
```powershell
python -m venv .venv                 # 1. create the virtual environment (Python >= 3.10)
.venv\Scripts\Activate.ps1           # 2. activate it
pip install -r requirements.txt      # 3. install the pinned dependencies
Copy-Item .env.example .env          # 4. create .env, then put your DeepSeek key in it
```

**Mac / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

The MCP SDK is pinned below 2.0 (`mcp==1.30.0`) because we use the classic
`from mcp.server.fastmcp import FastMCP` API.

`.env` is ignored by git. Never commit it.

_More sections (how to run each mode and the evaluation) will be added in later steps._
