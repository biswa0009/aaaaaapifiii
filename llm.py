"""
llm.py
------
Handles all communication with the Groq LLM:
  - Builds the structured prompt
  - Calls the Groq API (llama-3.3-70b-versatile)
  - Parses and validates the JSON response
  - Returns a clean dict ready for chart_generator.py
"""

import os
import json
import re
from groq import Groq
from database import get_schema_description, VALID_COLUMNS

# ── Groq client (reads GROQ_API_KEY from environment) ────────────────────────
_client: Groq | None = None


def get_groq_client() -> Groq:
    """Lazily initialise the Groq client once."""
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY environment variable is not set.\n"
                "Export it with:  export GROQ_API_KEY=gsk_..."
            )
        _client = Groq(api_key=api_key)
    return _client


# ── Prompt template ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are a business intelligence assistant. Your only job is to convert a
natural-language business question into a JSON object that describes:
  1. A valid SQLite SELECT query against the 'sales' table.
  2. The best Plotly chart type to visualise the result.
  3. Which column to use for the X axis.
  4. Which column to use for the Y axis.

DATABASE SCHEMA
{schema}

STRICT OUTPUT RULES
- Return ONLY a raw JSON object — no markdown, no code fences, no explanation.
- The JSON must have exactly these four keys:
    "sql_query"  : string  – a complete, valid SQLite SELECT statement
    "chart_type" : string  – one of: "bar", "line", "pie"
    "x_axis"     : string  – column name for X axis (must exist in query result)
    "y_axis"     : string  – column name for Y axis (must exist in query result)
- Choose chart type by these rules:
    "line" → time-series / trend data  (x_axis is date-like)
    "bar"  → category comparisons      (x_axis is categorical)
    "pie"  → part-to-whole / share     (question asks for %, share, proportion)
- Always alias aggregated columns so they match x_axis / y_axis exactly.
  Example:  SELECT customer_region, SUM(total_revenue) AS total_revenue ...
- Use strftime('%Y-%m', order_date) to group by month when the question is
  about monthly trends.
- NEVER invent columns that do not exist in the schema above.
- If the question cannot be answered from this schema, return:
  {{"error": "The dataset does not contain the requested information."}}
""".strip()

USER_PROMPT_TEMPLATE = "Question: {question}"


# ── Main function ─────────────────────────────────────────────────────────────
def ask_groq(question: str) -> dict:
    """
    Send *question* to Groq and return a validated dict with keys:
      sql_query, chart_type, x_axis, y_axis

    Raises ValueError with a user-friendly message on any failure.
    """
    client   = get_groq_client()
    schema   = get_schema_description()

    system_msg = SYSTEM_PROMPT.format(schema=schema)
    user_msg   = USER_PROMPT_TEMPLATE.format(question=question)

    # ── API call ──────────────────────────────────────────────────────────────
    try:
        response = client.chat.completions.create(
            model = "llama-3.3-70b-versatile",
            messages = [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            temperature = 0.1,   # Low temperature → deterministic SQL
            max_tokens  = 512,
        )
    except Exception as exc:
        raise ValueError(f"Groq API error: {exc}") from exc

    raw_text = response.choices[0].message.content.strip()
    print(f"[LLM] Raw response:\n{raw_text}\n")

    # ── JSON extraction ───────────────────────────────────────────────────────
    parsed = _extract_json(raw_text)

    # ── Error passthrough ─────────────────────────────────────────────────────
    if "error" in parsed:
        raise ValueError(parsed["error"])

    # ── Validate required keys ────────────────────────────────────────────────
    required = {"sql_query", "chart_type", "x_axis", "y_axis"}
    missing  = required - parsed.keys()
    if missing:
        raise ValueError(
            f"LLM response is missing required keys: {missing}\n"
            f"Raw response: {raw_text}"
        )

    # ── Normalise chart type ──────────────────────────────────────────────────
    parsed["chart_type"] = parsed["chart_type"].lower().strip()
    if parsed["chart_type"] not in {"bar", "line", "pie"}:
        parsed["chart_type"] = "bar"   # Safe fallback

    return parsed


# ── Helpers ───────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict:
    """
    Extract JSON from the LLM response.
    Handles cases where the model wraps the JSON in markdown fences.
    """
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object inside the text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not parse a valid JSON object from the LLM response.\n"
        f"Raw text: {text}"
    )
