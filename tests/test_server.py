"""STEP 3: test the MCP server through the real MCP protocol (stdio), without any LLM.

It starts server.py as a subprocess (like the agent will), calls every tool and the
resource, and compares the answers with values read directly from the CSV with pandas.

Run from the project root:
    python tests/test_server.py
"""

import asyncio
import json
import sys
from pathlib import Path

import pandas as pd
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = pd.read_csv(PROJECT_ROOT / "data" / "clean" / "mena_indicators.csv")

results = []  # (test name, passed)


def check(name: str, passed: bool, detail: str = "") -> None:
    """Record and print one test result."""
    results.append((name, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))


def csv_value(code: str, indicator: str, year: int) -> float:
    """Expected value, read straight from the CSV (independent of server.py)."""
    row = DATA[(DATA.country_code == code) & (DATA.indicator_code == indicator) & (DATA.year == year)]
    return float(row["value"].iloc[0])


async def call(session: ClientSession, tool: str, args: dict):
    """Call one tool. Return (is_error, parsed JSON or error text)."""
    result = await session.call_tool(tool, args)
    text = result.content[0].text if result.content else ""
    if result.isError:
        return True, text
    return False, result.structuredContent.get("result", result.structuredContent) \
        if result.structuredContent is not None else json.loads(text)


async def run_tests() -> None:
    """Start the server over stdio and run all checks."""
    params = StdioServerParameters(command=sys.executable, args=[str(PROJECT_ROOT / "server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discovery
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            check("list_tools", tools == ["compare_countries", "get_series", "get_value", "list_indicators"], str(tools))
            resources = [str(r.uri) for r in (await session.list_resources()).resources]
            check("list_resources", resources == ["data://schema"], str(resources))

            # Resource
            schema = json.loads((await session.read_resource("data://schema")).contents[0].text)
            check("schema: rows/years/countries", schema["rows"] == 400 and schema["years"] == {"from": 2010, "to": 2025}
                  and len(schema["countries"]) == 5, f"rows={schema['rows']}, years={schema['years']}")
            check("schema: gaps, source, licence", schema["known_gaps"] == "none (no missing values)"
                  and "World Bank" in schema["source"] and schema["licence"] == "CC BY 4.0", str(schema["known_gaps"]))

            # list_indicators
            err, inds = await call(session, "list_indicators", {})
            check("list_indicators: 5 with units", not err and len(inds) == 5 and all(i["unit"] for i in inds),
                  ", ".join(f"{i['key']}[{i['unit']}]" for i in inds) if not err else inds)

            # get_value: name, code, lower case, Egypt short name, population as int
            err, out = await call(session, "get_value", {"country": "Tunisia", "indicator": "inflation", "year": 2020})
            exp = csv_value("TUN", "FP.CPI.TOTL.ZG", 2020)
            check("get_value Tunisia inflation 2020", not err and out["value"] == exp, f"got {out if err else out['value']} [{'' if err else out['unit']}], csv {exp}")
            err, out = await call(session, "get_value", {"country": "mar", "indicator": "SL.UEM.TOTL.ZS", "year": 2021})
            exp = csv_value("MAR", "SL.UEM.TOTL.ZS", 2021)
            check("get_value 'mar' + WB code", not err and out["value"] == exp and "note" in out, f"got {out if err else out['value']}, csv {exp}")
            err, out = await call(session, "get_value", {"country": "egypt", "indicator": "population", "year": 2014})
            exp = csv_value("EGY", "SP.POP.TOTL", 2014)
            check("get_value 'egypt' population 2014 (int)", not err and out["value"] == int(exp) and isinstance(out["value"], int),
                  f"got {out if err else out['value']}, csv {exp}")

            # get_value: clear errors, never an invented value
            err, out = await call(session, "get_value", {"country": "France", "indicator": "inflation", "year": 2020})
            check("error: unknown country", err and "not in the dataset" in out, out)
            err, out = await call(session, "get_value", {"country": "Tunisia", "indicator": "inflation", "year": 2030})
            check("error: year out of range", err and "2010-2025" in out, out)
            err, out = await call(session, "get_value", {"country": "Tunisia", "indicator": "co2", "year": 2020})
            check("error: unknown indicator", err and "not in the dataset" in out, out)

            # get_series
            err, out = await call(session, "get_series", {"country": "JOR", "indicator": "gdp_growth"})
            exp = DATA[(DATA.country_code == "JOR") & (DATA.indicator_code == "NY.GDP.MKTP.KD.ZG")].sort_values("year")
            ok = not err and [p["value"] for p in out["series"]] == exp["value"].tolist() and out["series"][0]["year"] == 2010
            check("get_series Jordan gdp_growth 2010-2025", ok, f"{len(out['series'])} points" if not err else out)
            err, out = await call(session, "get_series", {"country": "Algeria", "indicator": "youth_unemployment",
                                                          "start_year": 2018, "end_year": 2020})
            check("get_series sub-range 2018-2020", not err and [p["year"] for p in out["series"]] == [2018, 2019, 2020],
                  str(out["series"]) if not err else out)
            err, out = await call(session, "get_series", {"country": "TUN", "indicator": "inflation", "start_year": 2020, "end_year": 2015})
            check("error: start_year > end_year", err and "after end_year" in out, out)

            # compare_countries
            err, out = await call(session, "compare_countries", {"indicator": "unemployment", "year": 2023})
            exp = DATA[(DATA.indicator_code == "SL.UEM.TOTL.ZS") & (DATA.year == 2023)].sort_values("value", ascending=False)
            ok = not err and [r["country_code"] for r in out["ranking"]] == exp["country_code"].tolist() \
                and [r["value"] for r in out["ranking"]] == exp["value"].tolist()
            check("compare_countries unemployment 2023", ok,
                  ", ".join(f"{r['rank']}.{r['country_code']}={r['value']}" for r in out["ranking"]) if not err else out)


def main() -> None:
    """Run the tests and exit with code 1 if any failed."""
    asyncio.run(run_tests())
    failed = [name for name, passed in results if not passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
