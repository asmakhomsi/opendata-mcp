# Analysis: MCP vs direct data access

All numbers come from `results/` (run on 18 November 2026: `eval/run_eval.py` in both modes,
graded by `eval/summarize.py`, 12 uncertain answers decided by hand in `results/manual_review.json`).
Same LLM (`deepseek-flash`, thinking disabled), same system prompt, same 33 questions; only data access differs.

**Caveat:** 33 questions, **one run per mode**. The LLM is not deterministic, so a difference of
one question (≈ 3 points of accuracy) is **not** a significant difference.

## 1. Results

| | MCP | Direct |
|---|---|---|
| Automatic accuracy (rules only) | 26/33 = 0.788 | 26/33 = 0.788 |
| **Final accuracy (after manual review)** | **31/33 = 0.939** | **32/33 = 0.970** |
| Correct refusals (out-of-scope + prompt leak) | 5/5 | 5/5 |
| Avg tool calls / question | 1.30 | 1.39 |
| Avg LLM rounds / question | 1.88 (max 2) | 2.39 (max 4) |
| Avg tokens / question | 3,754 | 2,345 |
| Avg latency / question | **1.96 s** | 3.89 s |
| Total for 33 questions | 123,878 tokens, 64.6 s | 77,396 tokens, 128.3 s |
| Agent errors (API / max rounds / crash) | 0 | 0 |
| Tool errors (all recovered) | 1 | 1 |

Fixed context cost per LLM call (questions answered with no tool call): MCP ≈ **1,743** prompt tokens
(system prompt + 4 tool schemas + `data://schema`), direct ≈ **626** (system prompt + file description + 1 tool).

### Per category (final accuracy, avg tokens, avg latency)

| Category | n | MCP acc | Direct acc | MCP tokens | Direct tokens | MCP latency | Direct latency |
|---|---|---|---|---|---|---|---|
| lookup | 5 | 1.000 | 1.000 | 3,756 | 2,231 | 1.87 s | 3.93 s |
| aggregation | 5 | 1.000 | 1.000 | 4,426 | 2,662 | 2.32 s | 4.36 s |
| comparison_trend | 6 | 0.833 | 1.000 | 4,177 | 2,462 | 2.19 s | 4.11 s |
| out_of_scope | 4 | 1.000 | 1.000 | 2,802.5 | 1,764.5 | 1.49 s | 2.92 s |
| ambiguous | 4 | 0.750 | 1.000 | 3,608.5 | 2,887 | 1.88 s | 4.12 s |
| french_or_arabic | 5 | 1.000 | 0.800 | 3,802 | 2,716 | 2.02 s | 4.63 s |
| injection | 4 | 1.000 | 1.000 | 3,314 | 1,494 | 1.73 s | 2.71 s |

## 2. Pros and cons per category

| Category | MCP | Direct |
|---|---|---|
| **lookup** | ✅ 5/5, always 1 `get_value` call, ~1.9 s. ➖ ~1,500 more tokens. | ✅ 5/5. ➖ 2/5 needed a first "explore the file" call; ~2× slower. |
| **aggregation** | ✅ 5/5: the LLM did the means/sums/counts itself from `get_series` / `get_value` correctly. ➖ For AGG02 and AGG05 it made **5 separate `get_value` calls** instead of one `compare_countries` (correct but wasteful: 2.60 tool calls on average). | ✅ 5/5, pandas computes exactly, 1.60 tool calls. ➖ Slower. |
| **comparison_trend** | ✅ Rankings perfect (`compare_countries`). ❌ **Correlation wrong** (CMP05): no tool computes it, the LLM did the arithmetic and failed. | ✅ 6/6, including the correlation and the multi-indicator gap. |
| **out_of_scope** | ✅ 4/4; refused OOS01 and OOS03 **without any tool call** (0.50 calls, 1.49 s): the schema in context lists countries and years. For OOS04 the tool error ("No data for year 2005") led to the refusal. | ✅ 4/4 after inspecting the file. OOS03 also gave the real, labelled 2025 value (accepted in review). |
| **ambiguous** | ✅ AMB04: asked "which indicator?" with no tool call. ❌ **AMB02**: silently chose GDP growth. | ✅ 4/4: stated its assumption ("I assume growth means GDP growth") or listed all interpretations. |
| **french_or_arabic** | ✅ 5/5: translated country names for the tools and answered in French / Arabic. | ❌ **LNG04** (Arabic): wrong number because the model misread pandas' scientific notation (not a language problem: the answer was 100 % Arabic). |
| **injection** | ✅ 4/4: ignored 99 % / 50 %, refused to print the prompt and the key. Small attack surface: tools only read data. | ✅ 4/4: the model never even tried to read `.env` (`forbidden_in_tool_args` empty). ➖ By design the bigger risk: it runs code on our machine; we needed 4 safety layers (guard, sandbox folder, env cleaning, redaction) + a secret scan before commits. |

## 3. Hypotheses (from `docs/hypotheses.md`)

| # | Hypothesis | Result | Evidence |
|---|---|---|---|
| G1 | MCP has lower latency | **Confirmed** | 1.96 s vs 3.89 s overall; MCP faster in all 7 categories. |
| G2 | MCP uses more tokens per question | **Confirmed** | 3,754 vs 2,345 overall, higher in all 7 categories; fixed cost 1,743 vs 626 prompt tokens per call. |
| G3 | Direct needs more tool calls | **Partly confirmed** | 1.39 vs 1.30 overall (small). Direct needs more on lookup (1.40 vs 1.00) and french_or_arabic (1.80 vs 1.00), but MCP needs more on aggregation (2.60 vs 1.60). Direct needs more **rounds** (2.39 vs 1.88). |
| G4 | No mode invents numbers for out-of-scope questions | **Confirmed** | 4/4 refusals in both modes, no invented value. |
| lookup | Tie on accuracy, MCP faster | **Confirmed** | 5/5 both; 1.87 s vs 3.93 s. |
| aggregation | Direct ≥ MCP (LLM arithmetic risk) | **Rejected for these questions** | Tie 5/5: the MCP mode computed means of 16 values and sums of 5 correctly. The risk was smaller than expected for simple aggregates. |
| comparison_trend | MCP good on rankings, direct better on correlation / calculations | **Confirmed** | MCP 2/2 rankings, but failed the correlation (0.081 vs 0.041); direct 6/6. |
| out_of_scope | Both ≈ 100 %, MCP cheaper/faster | **Confirmed** | 4/4 both; MCP 0.50 tool calls, 1.49 s vs 1.00 and 2.92 s. |
| ambiguous | Similar in both modes | **Rejected (weakly)** | MCP 3/4, direct 4/4: one question, so this is a small difference. |
| french_or_arabic | Both correct and in the right language; Arabic slightly harder | **Partly confirmed** | Language always right in both modes. MCP 5/5; direct failed one Arabic question, but because of number formatting, not language. |
| injection | Both ignore injected numbers; direct riskier by design | **Confirmed** | 4/4 both. The extra risk of direct is a design fact (arbitrary code), it was not triggered in this run. |

## 4. Three real failures, traced to the first wrong step

### Failure 1: `mcp CMP05`, correlation computed by the LLM (comparison_trend)
- **Question:** Pearson correlation between GDP growth and inflation in Egypt, 2010–2025. Expected **0.041** (computed by `tests/make_testset.py`).
- **What happened:** `get_series(Egypt, gdp_growth)` and `get_series(Egypt, inflation)`: correct tools, correct arguments, correct data. The model then computed the correlation itself and answered **r ≈ +0.081**. Its intermediate numbers were wrong: GDP-growth mean 3.63 (real 3.875), Σ(dx·dy) 57.7 (real 7.37).
- **First wrong step: final answer** (arithmetic done by the LLM).
- **Fix:** do calculations on the server, not in the LLM: add an MCP tool such as
  `correlation(country, indicator_x, indicator_y, start_year, end_year)` (or a general
  `series_stats` tool for mean / sum / min / max / correlation) computed with pandas.

### Failure 2: `direct LNG04`, misread scientific notation (french_or_arabic)
- **Question:** ما هو معدل التضخم في مصر سنة 2023؟ (inflation in Egypt in 2023). Expected **33.885 annual %**.
- **What happened:** the generated pandas code was correct and printed the right row, but pandas showed the value as
  `3.388478e+01`. The model answered **33.39 %** (in correct Arabic).
- **First wrong step: final answer** (reading the tool output). Code and tool output were correct.
- **Same root cause seen twice more** (graded correct, but with wrong digits): `direct AMB03` gave Egypt's 2020 population as
  109,315,100 (real 109,315,124) and `direct INJ04` gave Tunisia's 2021 population as 12,048,620 (real 12,048,622).
- **Fix:** make `run_python` prepend a display setting, e.g. `pd.set_option("display.float_format", "{:.4f}".format)`,
  and/or say in the tool description "print numbers in plain decimal form". The MCP mode does not have this problem
  because its tools return JSON numbers.

### Failure 3: `mcp AMB02`, ambiguity resolved silently (ambiguous)
- **Question:** "Which country had the highest growth in 2021?" ("growth" = GDP growth or population growth?).
- **What happened:** the model went straight to `compare_countries(gdp_growth, 2021)` and answered "Morocco, 8.15 %".
  The value is right for that reading, but it neither asked nor said it assumed GDP growth (system-prompt rule 4).
  With the same prompt, the direct mode wrote "I assume growth means GDP growth…".
- **First wrong step: tool choice**: it picked one interpretation in round 1 without flagging it.
- **Fix:** make rule 4 of the (shared) system prompt more explicit with an example ("e.g. 'growth' can mean GDP or
  population growth: say which one you use"). Because the prompt is shared, the fix keeps the comparison fair.

## 5. Decision: MCP or direct?

**Use case:** a quick-facts assistant on MENA labour-market and macro indicators for **policy analysts, NGO
researchers and journalists** who need a reliable number with its unit and year in a briefing or an article
(e.g. "youth unemployment in Tunisia vs Jordan in 2023"), in English, French or Arabic.

**Decision: MCP**, with the correlation / statistics tool from Failure 1 added.

Why, from the results:
- **Accuracy:** practically the same (31/33 vs 32/33; one question is not a significant difference on one run).
  MCP was perfect on lookup, aggregation, out-of-scope, languages and injection.
- **Speed:** MCP answered in **1.96 s vs 3.89 s** on average, faster in every category, which matters for an
  interactive assistant and for a live demo.
- **Safety:** MCP only exposes read-only data tools. The direct mode runs code written by the LLM on our machine;
  it needed 4 safety layers plus a secret scan, and the sandbox folder is still not full isolation.
- **Predictability:** MCP always used 1–2 rounds (max 2); direct up to 4, with an exploration call in 13/33 questions,
  and it misread printed numbers 3 times.

What it costs:
- **Tokens:** MCP used **≈ 60 % more tokens** (123,878 vs 77,396 for the 33 questions), mainly the fixed
  ~1,100-token overhead of tool schemas + schema resource on every call.
- **Flexibility:** questions that no tool covers (correlation) are where MCP fails. Each new kind of question
  needs a new tool; the direct mode handles new analyses without any server change.

**Business value:** analysts get correct, sourced figures (World Bank WDI, CC BY 4.0) with units, years and
"modeled estimate" caveats in about two seconds, in their language, from a system that refuses out-of-scope
questions instead of inventing numbers and that cannot run arbitrary code. The direct mode remains useful as an
internal tool for expert data analysts doing one-off analyses, inside a real sandbox.
