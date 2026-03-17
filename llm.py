"""
llm.py  (v4)
------------
Groq API integration — natural language → structured JSON (sql + chart metadata).

Changes in v4:
  - Model: llama-3.3-70b-versatile
  - Prompt: 5 hard SQL rules, explicit GROUP BY requirement, title field
  - Filter context: active filters injected as hint so LLM incorporates them
  - LIMIT-1 safety strip applied post-parse
"""

import os
import json
import re
from groq import Groq
from database import get_schema_description

_client: Groq | None = None


def get_groq_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY environment variable is not set.\n"
                "Set it with:  export GROQ_API_KEY=gsk_..."
            )
        _client = Groq(api_key=api_key)
    return _client


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a business intelligence SQL expert. Your ONLY output is a raw JSON object.
No markdown, no explanation, no code fences — just the JSON.

DATABASE SCHEMA
{schema}

OUTPUT — exactly these five keys:
{{
  "sql_query"  : "...",   -- valid SQLite SELECT on the 'sales' table
  "chart_type" : "...",   -- one of: bar | line | pie | area
  "x_axis"     : "...",   -- column name for X (must exist in SELECT result)
  "y_axis"     : "...",   -- column name for Y (must exist in SELECT result)
  "title"      : "..."    -- short chart title, max 8 words
}}

═══ MANDATORY SQL RULES — violating any rule produces a wrong answer ═══

RULE 1 ── ALWAYS GROUP BY when comparing groups.
  Questions comparing regions, categories, payment methods, or any other
  dimension MUST return ALL groups using GROUP BY.
  ✓ CORRECT: SELECT customer_region, SUM(total_revenue) AS total_revenue
             FROM sales GROUP BY customer_region ORDER BY total_revenue DESC
  ✗ WRONG:   ... ORDER BY total_revenue DESC LIMIT 1

RULE 2 ── NEVER use LIMIT 1 on comparison charts.
  "Which region has the most revenue?" → return ALL regions.
  Only use LIMIT N when the user explicitly asks for "top N" (N > 1).

RULE 3 ── Always alias aggregated expressions to match x_axis / y_axis.
  SUM(total_revenue) AS total_revenue   ← alias matches y_axis value

RULE 4 ── Time-series grouping:
  Monthly  → strftime('%Y-%m', order_date) AS order_date
  Yearly   → strftime('%Y',    order_date) AS order_date
  Always ORDER BY order_date ASC for trends.

RULE 5 ── For "top N" use:  ORDER BY … DESC LIMIT N

CHART TYPE RULES:
  bar  → comparing categories (regions, categories, payment methods)
  line → trends over time
  pie  → share / proportion / % breakdown
  area → cumulative trends

FILTER CONTEXT (if provided):
  If active filter context is present in the user message, add a WHERE
  clause matching those filters to the SQL.

ERROR: If the question cannot be answered from this schema return:
  {{"error": "The dataset does not contain the requested information."}}
""".strip()


# ── Main public function ──────────────────────────────────────────────────────
def ask_groq(question: str, filter_context: str = "") -> dict:
    """
    Send question + optional filter context to Groq.
    Returns validated dict: {sql_query, chart_type, x_axis, y_axis, title}
    Raises ValueError on any failure.
    """
    client = get_groq_client()
    schema = get_schema_description()

    system_msg = SYSTEM_PROMPT.format(schema=schema)

    user_parts = [f"Question: {question}"]
    if filter_context:
        user_parts.append(f"Context: {filter_context}")
    user_msg = "\n".join(user_parts)

    try:
        response = client.chat.completions.create(
            model       = "llama-3.3-70b-versatile",
            messages    = [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            temperature = 0.0,
            max_tokens  = 600,
        )
    except Exception as exc:
        raise ValueError(f"Groq API error: {exc}") from exc

    raw = response.choices[0].message.content.strip()
    print(f"[LLM] Response: {raw[:200]}")

    parsed = _extract_json(raw)

    if "error" in parsed:
        raise ValueError(parsed["error"])

    required = {"sql_query", "chart_type", "x_axis", "y_axis"}
    missing  = required - parsed.keys()
    if missing:
        raise ValueError(f"LLM missing keys {missing}. Raw: {raw[:300]}")

    # Normalise chart type
    parsed["chart_type"] = parsed["chart_type"].lower().strip()
    if parsed["chart_type"] not in {"bar", "line", "pie", "area", "scatter"}:
        parsed["chart_type"] = "bar"

    # Ensure title
    if not parsed.get("title", "").strip():
        parsed["title"] = question[:60]

    # Safety: strip LIMIT 1 from GROUP BY queries
    sql = parsed["sql_query"]
    if re.search(r"GROUP\s+BY", sql, re.IGNORECASE) and \
       re.search(r"\bLIMIT\s+1\b", sql, re.IGNORECASE):
        sql = re.sub(r"\s*LIMIT\s+1\b", "", sql, flags=re.IGNORECASE).strip()
        parsed["sql_query"] = sql
        print("[LLM] Stripped LIMIT 1 from GROUP BY query.")

    return parsed


# ── JSON extractor ────────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Cannot parse JSON from LLM response: {text[:300]}")
