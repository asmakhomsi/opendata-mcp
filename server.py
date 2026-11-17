"""STEP 3: our MCP server (FastMCP, stdio) for the MENA open data.

It loads data/clean/mena_indicators.csv once and exposes:
  Tools    : list_indicators, get_value, get_series, compare_countries
  Resource : data://schema  (columns, units, countries, years, gaps, source, licence)

Tools only return values that are in the CSV. If something is not in the data,
they raise a clear error (the MCP client receives it as an error result).

Run (normally started by the agent or the MCP Inspector, not by hand):
    python server.py
"""

import json
from pathlib import Path

import pandas as pd
from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_FILE = PROJECT_ROOT / "data" / "clean" / "mena_indicators.csv"

# Short, easy names for the indicators (same names as the raw files), mapped to World Bank codes.
INDICATOR_KEYS = {
    "unemployment": "SL.UEM.TOTL.ZS",
    "youth_unemployment": "SL.UEM.1524.ZS",
    "gdp_growth": "NY.GDP.MKTP.KD.ZG",
    "inflation": "FP.CPI.TOTL.ZG",
    "population": "SP.POP.TOTL",
}
MODELED_NOTE = "ILO modeled estimate (2024-2025 values are estimates)."

# log_level=WARNING hides the "Processing request ..." info lines in the terminal.
mcp = FastMCP("mena-open-data", log_level="WARNING")


# ---------- data loading and lookups ----------

def load_data() -> pd.DataFrame:
    """Load the clean CSV built in STEP 2."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"{DATA_FILE} not found. Run: python scripts/build_dataset.py")
    return pd.read_csv(DATA_FILE)


DATA = load_data()
YEAR_MIN, YEAR_MAX = int(DATA["year"].min()), int(DATA["year"].max())


def build_country_lookup(data: pd.DataFrame) -> dict:
    """Map every accepted spelling (lower case) to a country code.

    Accepted: the ISO3 code ("TUN"), the full World Bank name ("Egypt, Arab Rep.")
    and the part before the comma ("Egypt").
    """
    lookup = {}
    for code, name in data[["country_code", "country_name"]].drop_duplicates().itertuples(index=False):
        lookup[code.lower()] = code
        lookup[name.lower()] = code
        lookup[name.split(",")[0].strip().lower()] = code
    return lookup


COUNTRY_LOOKUP = build_country_lookup(DATA)
COUNTRY_NAMES = dict(DATA[["country_code", "country_name"]].drop_duplicates().itertuples(index=False))


def resolve_country(country: str) -> str:
    """Return the country code for a name or code (case-insensitive), or raise a clear error."""
    code = COUNTRY_LOOKUP.get(str(country).strip().lower())
    if code is None:
        available = ", ".join(f"{name} ({code})" for code, name in COUNTRY_NAMES.items())
        raise ValueError(f"Country '{country}' is not in the dataset. Available: {available}.")
    return code


def resolve_indicator(indicator: str) -> str:
    """Return the indicator code for a short key or a World Bank code, or raise a clear error."""
    text = str(indicator).strip()
    if text.lower() in INDICATOR_KEYS:
        return INDICATOR_KEYS[text.lower()]
    for code in INDICATOR_KEYS.values():
        if text.upper() == code:
            return code
    keys = ", ".join(f"{key} ({code})" for key, code in INDICATOR_KEYS.items())
    raise ValueError(f"Indicator '{indicator}' is not in the dataset. Available: {keys}.")


def check_year(year: int) -> None:
    """Raise a clear error if the year is outside the data."""
    if not YEAR_MIN <= int(year) <= YEAR_MAX:
        raise ValueError(f"No data for year {year}. The dataset covers {YEAR_MIN}-{YEAR_MAX} only.")


def indicator_info(code: str) -> dict:
    """Name, unit and note for one indicator code."""
    row = DATA[DATA["indicator_code"] == code].iloc[0]
    info = {"indicator_code": code, "indicator_name": row["indicator_name"], "unit": row["unit"]}
    if code.startswith("SL.UEM"):
        info["note"] = MODELED_NOTE
    return info


def clean_value(value: float, unit: str):
    """Population is a count, so show it as a whole number; keep other values unchanged."""
    if pd.isna(value):
        return None
    return int(value) if unit == "people" else float(value)


# ---------- MCP tools ----------

@mcp.tool()
def list_indicators() -> list[dict]:
    """List the 5 indicators in the dataset with their short key, World Bank code, name and unit.

    Use the short key (e.g. "inflation") or the code in the other tools.
    """
    return [{"key": key, **indicator_info(code)} for key, code in INDICATOR_KEYS.items()]


@mcp.tool()
def get_value(country: str, indicator: str, year: int) -> dict:
    """Get one value for one country, one indicator and one year.

    Args:
        country: English country name or ISO3 code, e.g. "Tunisia" or "TUN" (case-insensitive).
        indicator: short key (unemployment, youth_unemployment, gdp_growth, inflation, population)
                   or World Bank code, e.g. "FP.CPI.TOTL.ZG".
        year: a year between 2010 and 2025.
    """
    code, ind = resolve_country(country), resolve_indicator(indicator)
    check_year(year)
    rows = DATA[(DATA["country_code"] == code) & (DATA["indicator_code"] == ind) & (DATA["year"] == int(year))]
    info = indicator_info(ind)
    value = clean_value(rows["value"].iloc[0], info["unit"]) if len(rows) else None
    if value is None:
        raise ValueError(f"No data for {COUNTRY_NAMES[code]}, {ind}, {year} (missing in the source).")
    return {"country_code": code, "country_name": COUNTRY_NAMES[code], "year": int(year), "value": value, **info}


@mcp.tool()
def get_series(country: str, indicator: str, start_year: int = 2010, end_year: int = 2025) -> dict:
    """Get a yearly time series for one country and one indicator.

    Args:
        country: English country name or ISO3 code (case-insensitive).
        indicator: short key or World Bank code (see list_indicators).
        start_year: first year (default 2010, minimum 2010).
        end_year: last year (default 2025, maximum 2025).
    """
    code, ind = resolve_country(country), resolve_indicator(indicator)
    check_year(start_year)
    check_year(end_year)
    if int(start_year) > int(end_year):
        raise ValueError(f"start_year ({start_year}) is after end_year ({end_year}).")
    rows = DATA[
        (DATA["country_code"] == code) & (DATA["indicator_code"] == ind)
        & (DATA["year"].between(int(start_year), int(end_year)))
    ].sort_values("year")
    info = indicator_info(ind)
    series = [{"year": int(r.year), "value": clean_value(r.value, info["unit"])} for r in rows.itertuples()]
    return {"country_code": code, "country_name": COUNTRY_NAMES[code], **info, "series": series}


@mcp.tool()
def compare_countries(indicator: str, year: int) -> dict:
    """Rank all 5 countries for one indicator in one year (rank 1 = highest value).

    Args:
        indicator: short key or World Bank code (see list_indicators).
        year: a year between 2010 and 2025.
    """
    ind = resolve_indicator(indicator)
    check_year(year)
    rows = DATA[(DATA["indicator_code"] == ind) & (DATA["year"] == int(year))].dropna(subset=["value"])
    rows = rows.sort_values("value", ascending=False)
    info = indicator_info(ind)
    ranking = [
        {"rank": i, "country_code": r.country_code, "country_name": r.country_name,
         "value": clean_value(r.value, info["unit"])}
        for i, r in enumerate(rows.itertuples(), start=1)
    ]
    return {"year": int(year), **info, "ranking": ranking}


# ---------- MCP resource ----------

def build_schema() -> dict:
    """Describe the dataset: columns, units, countries, years, gaps, source and licence."""
    missing = DATA[DATA["value"].isna()]
    gaps = [f"{r.country_code} {r.indicator_code} {r.year}" for r in missing.itertuples()]
    return {
        "file": "data/clean/mena_indicators.csv",
        "columns": list(DATA.columns),
        "rows": len(DATA),
        "countries": [{"code": code, "name": name} for code, name in COUNTRY_NAMES.items()],
        "years": {"from": YEAR_MIN, "to": YEAR_MAX},
        "indicators": list_indicators(),
        "known_gaps": gaps if gaps else "none (no missing values)",
        "notes": [
            "Unemployment indicators are ILO modeled estimates; 2024-2025 values are estimates.",
            "Egypt's official name in the data is 'Egypt, Arab Rep.'.",
        ],
        "source": "World Bank, World Development Indicators (bulk CSV, last updated 2026-11-11)",
        "licence": "CC BY 4.0",
    }


@mcp.resource("data://schema", mime_type="application/json")
def schema() -> str:
    """Schema and metadata of the MENA indicators dataset."""
    return json.dumps(build_schema(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")  # stdio: the client starts this file as a subprocess
