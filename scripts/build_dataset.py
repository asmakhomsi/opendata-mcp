"""STEP 2: build one clean, tidy (long) CSV from the 5 raw World Bank files.

Input : data/raw/*.csv   (World Bank WDI bulk CSV, wide: one column per year)
Output: data/clean/mena_indicators.csv with columns
        country_code, country_name, indicator_code, indicator_name, unit, year, value

Rules: keep only 5 countries and years 2010-2025; never fill missing values
(a gap stays empty and is reported). Then print a data report.

Run from the project root:
    python scripts/build_dataset.py
"""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CLEAN_FILE = PROJECT_ROOT / "data" / "clean" / "mena_indicators.csv"

COUNTRY_CODES = ["DZA", "EGY", "JOR", "MAR", "TUN"]
FIRST_YEAR, LAST_YEAR = 2010, 2025

# file name -> (expected indicator code, unit).
# The raw files have no unit column. Units are taken from the indicator names in the
# files themselves (the text in brackets); population is a count of people.
RAW_FILES = {
    "unemployment_total.csv": ("SL.UEM.TOTL.ZS", "% of total labor force"),
    "youth_unemployment.csv": ("SL.UEM.1524.ZS", "% of total labor force ages 15-24"),
    "gdp_growth.csv": ("NY.GDP.MKTP.KD.ZG", "annual %"),
    "inflation.csv": ("FP.CPI.TOTL.ZG", "annual %"),
    "population.csv": ("SP.POP.TOTL", "people"),
}

OUTPUT_COLUMNS = ["country_code", "country_name", "indicator_code", "indicator_name", "unit", "year", "value"]


def read_raw_file(path: Path) -> pd.DataFrame:
    """Read one World Bank bulk CSV (4 lines of text before the header, UTF-8 with BOM)."""
    if not path.exists():
        sys.exit(f"ERROR: raw file not found: {path}")
    df = pd.read_csv(path, skiprows=4, encoding="utf-8-sig")

    # Drop the empty trailing column(s) that the World Bank export adds ("Unnamed: 70").
    unnamed = [col for col in df.columns if str(col).startswith("Unnamed")]
    for col in unnamed:
        if not df[col].isna().all():
            sys.exit(f"ERROR: column {col!r} in {path.name} is not empty; check the file.")
    return df.drop(columns=unnamed)


def to_long(df: pd.DataFrame, file_name: str, expected_code: str, unit: str) -> pd.DataFrame:
    """Keep our countries and years, check the file, and turn it from wide to long."""
    codes_in_file = df["Indicator Code"].unique().tolist()
    if codes_in_file != [expected_code]:
        sys.exit(f"ERROR: {file_name} has indicator codes {codes_in_file}, expected {expected_code}.")

    df = df[df["Country Code"].isin(COUNTRY_CODES)]
    missing_countries = set(COUNTRY_CODES) - set(df["Country Code"])
    if missing_countries:
        sys.exit(f"ERROR: {file_name} has no row for {sorted(missing_countries)}.")

    year_columns = [str(year) for year in range(FIRST_YEAR, LAST_YEAR + 1)]
    missing_years = [year for year in year_columns if year not in df.columns]
    if missing_years:
        sys.exit(f"ERROR: {file_name} has no column for years {missing_years}.")

    long_df = df.melt(
        id_vars=["Country Code", "Country Name", "Indicator Code", "Indicator Name"],
        value_vars=year_columns,
        var_name="year",
        value_name="value",
    )
    long_df = long_df.rename(
        columns={
            "Country Code": "country_code",
            "Country Name": "country_name",
            "Indicator Code": "indicator_code",
            "Indicator Name": "indicator_name",
        }
    )
    long_df["unit"] = unit
    long_df["year"] = long_df["year"].astype(int)
    return long_df[OUTPUT_COLUMNS]


def build_dataset() -> pd.DataFrame:
    """Read all 5 raw files and stack them into one long table."""
    parts = []
    for file_name, (expected_code, unit) in RAW_FILES.items():
        raw = read_raw_file(RAW_DIR / file_name)
        parts.append(to_long(raw, file_name, expected_code, unit))
    data = pd.concat(parts, ignore_index=True)
    return data.sort_values(["indicator_code", "country_code", "year"]).reset_index(drop=True)


def print_report(data: pd.DataFrame) -> None:
    """Print a short report on the clean data: size, years, units and missing values."""
    print("=== Data report ===")
    print(f"Rows: {len(data)}  (expected {len(COUNTRY_CODES)} countries x {len(RAW_FILES)} indicators "
          f"x {LAST_YEAR - FIRST_YEAR + 1} years = "
          f"{len(COUNTRY_CODES) * len(RAW_FILES) * (LAST_YEAR - FIRST_YEAR + 1)})")
    print(f"Years: {data['year'].min()} to {data['year'].max()}")
    print(f"Countries: {data[['country_code', 'country_name']].drop_duplicates().values.tolist()}")

    print("\nIndicators and units:")
    for row in data[["indicator_code", "indicator_name", "unit"]].drop_duplicates().itertuples(index=False):
        print(f"  {row.indicator_code:<18} [{row.unit}]  {row.indicator_name}")

    print("\nMissing values per country x indicator (2010-2025):")
    missing = data["value"].isna().groupby([data["country_code"], data["indicator_code"]]).sum().unstack()
    print(missing.to_string())
    print(f"Total missing: {int(data['value'].isna().sum())}")

    print("\nLast year with a value, per country x indicator:")
    last_year = data.dropna(subset=["value"]).groupby(["country_code", "indicator_code"])["year"].max().unstack()
    print(last_year.to_string())

    print("\nDuplicate (country, indicator, year) rows:",
          int(data.duplicated(["country_code", "indicator_code", "year"]).sum()))


def main() -> None:
    """Build the clean CSV, save it and print the report."""
    data = build_dataset()
    CLEAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(CLEAN_FILE, index=False, encoding="utf-8")
    print(f"Saved {CLEAN_FILE.relative_to(PROJECT_ROOT)}\n")
    print_report(data)


if __name__ == "__main__":
    main()
