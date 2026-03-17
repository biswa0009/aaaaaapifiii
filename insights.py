"""
insights.py
-----------
Uses Groq to generate a short, plain-English business insight paragraph
for any chart result.  Called after a successful SQL + chart render.

The insight is kept to 3-5 sentences and focuses on:
  - The standout finding (highest / lowest / trend direction)
  - A comparison or contrast across categories if relevant
  - A brief actionable observation

The function is deliberately fast: temperature=0 and max_tokens=256
so it adds value without noticeable latency.
"""

import pandas as pd
from llm import get_groq_client          # re-uses the already-initialised client


# ── Prompt ────────────────────────────────────────────────────────────────────
_INSIGHT_SYSTEM = """
You are a concise business analyst. You will be given:
  1. The user's original business question.
  2. A small data table (CSV format) that answers the question.

Write a business insight in EXACTLY 3-5 sentences that:
  - Starts with the single most important finding (use specific numbers).
  - Highlights any notable contrast, gap, or trend in the data.
  - Ends with one short, practical observation or recommendation.

Rules:
  - Plain English only — no bullet points, no markdown, no headers.
  - Be specific: use the actual values from the data.
  - Never exceed 5 sentences.
  - Never repeat the question verbatim.
""".strip()

_INSIGHT_USER = """
Question : {question}

Data (CSV):
{csv_snippet}
""".strip()


# ── Public function ───────────────────────────────────────────────────────────
def generate_insight(question: str, df: pd.DataFrame, y_col: str) -> str:
    """
    Parameters
    ----------
    question : the original user question
    df       : the DataFrame returned by the SQL query
    y_col    : name of the numeric / value column

    Returns
    -------
    A 3-5 sentence insight string, or an empty string on any failure
    (insight is non-critical — failures must never break the main flow).
    """
    try:
        client = get_groq_client()
    except EnvironmentError:
        return ""          # No API key → silently skip insights

    # ── Prepare a compact CSV snippet (max 20 rows to stay within tokens) ──
    df_snippet = df.head(20).copy()

    # Round floats for readability
    for col in df_snippet.select_dtypes(include="float").columns:
        df_snippet[col] = df_snippet[col].round(2)

    csv_snippet = df_snippet.to_csv(index=False)

    user_msg = _INSIGHT_USER.format(
        question    = question,
        csv_snippet = csv_snippet,
    )

    try:
        response = get_groq_client().chat.completions.create(
            model = "llama-3.3-70b-versatile",
            messages    = [
                {"role": "system", "content": _INSIGHT_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            temperature = 0.3,
            max_tokens  = 256,
        )
        insight = response.choices[0].message.content.strip()
        return insight

    except Exception as exc:
        # Insight is a nice-to-have — never crash the app for it
        print(f"[Insights] Skipped due to error: {exc}")
        return ""
