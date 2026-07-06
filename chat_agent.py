"""
chat_agent.py
-------------
Conversational AI agent connected to any pandas DataFrame.

Supports natural-language questions about the dataset with per-response
Plotly visualisations embedded in the chat thread.

Public API
----------
  detect_question_intent(question, col_map) -> dict
  build_agent_context(df, col_map, intent)  -> str
  build_chart_from_intent(df, col_map, intent, palette, dark) -> go.Figure | None
  ask_agent(question, df, col_map, chat_history)              -> AgentResponse
"""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ── AgentResponse ──────────────────────────────────────────────────────────────

@dataclass
class AgentResponse:
    """Structured output from ask_agent()."""
    question:    str              = ""
    answer:      str              = ""
    reasoning:   str              = ""
    fig:         Optional[object] = None
    chart_title: str              = ""
    intent:      str              = "general"
    error:       str              = ""


# ── Intent detector ────────────────────────────────────────────────────────────

_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("forecast",        ["forecast", "predict", "next month", "next quarter", "future", "projection"]),
    ("compare_regions", ["compare region", "by region", "regional", "which region", "region breakdown"]),
    ("best_product",    ["best product", "top product", "worst product", "bottom product",
                         "which product", "best category", "top category", "performing product",
                         "best seller", "highest revenue"]),
    ("monthly_revenue", ["monthly revenue", "monthly sales", "monthly trend", "revenue by month",
                         "show month", "month over month", "revenue trend", "sales trend",
                         "revenue over time", "sales over time"]),
    ("sales_decrease",  ["decrease", "decline", "drop", "fell", "why", "reason", "cause",
                         "less than", "lower", "worst month", "poor performance"]),
    ("distribution",    ["distribution", "histogram", "spread", "variance", "how distributed"]),
    ("correlation",     ["correlation", "relationship", "related", "correlate", "heatmap"]),
    ("compare_generic", ["compare", "breakdown", "by payment", "by category", "top 10", "top 5"]),
]


def detect_question_intent(question: str, col_map: dict) -> dict:
    """
    Classify the user question into one of the supported intents.

    Returns
    -------
    {
      "intent": str,
      "date_col": str | None,
      "value_col": str | None,
      "product_col": str | None,
      "region_col": str | None,
    }
    """
    q_lower = question.lower()
    detected = "general"
    for intent_name, keywords in _INTENT_PATTERNS:
        if any(kw in q_lower for kw in keywords):
            detected = intent_name
            break

    return {
        "intent":      detected,
        "date_col":    col_map.get("date"),
        "value_col":   col_map.get("value"),
        "product_col": col_map.get("product"),
        "region_col":  col_map.get("region"),
    }


# ── Context builder ────────────────────────────────────────────────────────────

def build_agent_context(df: pd.DataFrame, col_map: dict, intent: dict) -> str:
    """
    Build a concise, LLM-readable context block from the DataFrame and intent.
    """
    parts: list[str] = []

    n_rows, n_cols = df.shape
    parts.append(f"Dataset: {n_rows:,} rows x {n_cols} columns")
    parts.append(f"Columns: {', '.join(df.columns.tolist())}")

    date_col    = intent.get("date_col")
    value_col   = intent.get("value_col")
    product_col = intent.get("product_col")
    region_col  = intent.get("region_col")

    # Numeric summary for value column
    if value_col and value_col in df.columns:
        v = pd.to_numeric(df[value_col], errors="coerce").dropna()
        parts.append(
            f"Primary metric ({value_col}): "
            f"total={v.sum():,.0f}, mean={v.mean():,.2f}, "
            f"min={v.min():,.2f}, max={v.max():,.2f}"
        )

    # Monthly trend (last 6 periods)
    if date_col and value_col and date_col in df.columns and value_col in df.columns:
        try:
            tmp = df[[date_col, value_col]].copy()
            tmp[date_col]  = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
            tmp = tmp.dropna().set_index(date_col).sort_index()
            monthly = tmp[value_col].resample("ME").sum()
            if not monthly.empty:
                last6 = monthly.tail(6)
                trend_str = "; ".join(
                    f"{str(p)[:7]}={v:,.0f}" for p, v in last6.items()
                )
                parts.append(f"Last 6 monthly totals: {trend_str}")
                if len(monthly) > 1:
                    pct = monthly.pct_change().iloc[-1] * 100
                    direction = "up" if pct > 0 else "down"
                    parts.append(f"Latest MoM change: {pct:+.1f}% ({direction})")
        except Exception:
            pass

    # Product breakdown (top 5)
    if product_col and value_col and product_col in df.columns and value_col in df.columns:
        try:
            grp = (
                df.groupby(product_col)[value_col]
                .sum()
                .sort_values(ascending=False)
            )
            top5 = "; ".join(f"{k}={v:,.0f}" for k, v in grp.head(5).items())
            parts.append(f"Top products by {value_col}: {top5}")
        except Exception:
            pass

    # Region breakdown
    if region_col and value_col and region_col in df.columns and value_col in df.columns:
        try:
            grp = (
                df.groupby(region_col)[value_col]
                .sum()
                .sort_values(ascending=False)
            )
            r_str = "; ".join(f"{k}={v:,.0f}" for k, v in grp.items())
            parts.append(f"Region breakdown ({value_col}): {r_str}")
        except Exception:
            pass

    return "\n".join(parts)


# ── Chart builder ──────────────────────────────────────────────────────────────

_DEFAULT_PALETTE = ["#6366F1", "#22C55E", "#F59E0B", "#EF4444", "#06B6D4", "#A855F7"]


def _get_chart_layout(dark: bool) -> dict:
    bg   = "#111827" if dark else "#FFFFFF"
    grid = "rgba(255,255,255,0.06)" if dark else "rgba(0,0,0,0.06)"
    txt  = "#E5E7EB" if dark else "#1F2937"
    return dict(
        paper_bgcolor = bg,
        plot_bgcolor  = bg,
        font          = dict(family="Inter, sans-serif", color=txt, size=12),
        xaxis         = dict(gridcolor=grid, linecolor=grid, zeroline=False),
        yaxis         = dict(gridcolor=grid, linecolor=grid, zeroline=False),
        margin        = dict(l=40, r=20, t=40, b=40),
        height        = 360,
    )


def build_chart_from_intent(
    df:         pd.DataFrame,
    col_map:    dict,
    intent:     dict,
    palette:    list | None = None,
    dark:       bool = True,
) -> tuple:
    """
    Build the most appropriate Plotly figure for the given intent.

    Returns (fig, chart_title) -- fig is None if no chart can be built.
    """
    pal        = palette or _DEFAULT_PALETTE
    layout     = _get_chart_layout(dark)
    intent_key = intent.get("intent", "general")

    date_col    = intent.get("date_col")
    value_col   = intent.get("value_col")
    product_col = intent.get("product_col")
    region_col  = intent.get("region_col")

    if intent_key == "forecast":
        return _chart_forecast(df, date_col, value_col, pal, layout)

    if intent_key in ("monthly_revenue", "sales_decrease"):
        return _chart_monthly_trend(df, date_col, value_col, pal, layout)

    if intent_key == "compare_regions":
        return _chart_bar(df, region_col, value_col, pal, layout, "Region Comparison")

    if intent_key == "best_product":
        return _chart_bar(df, product_col, value_col, pal, layout, "Product Performance")

    if intent_key == "distribution":
        return _chart_histogram(df, value_col, pal, layout)

    if intent_key == "correlation":
        return _chart_correlation(df, layout)

    if intent_key == "compare_generic":
        dim = product_col or region_col
        return _chart_bar(df, dim, value_col, pal, layout,
                          f"{_pretty(dim or 'Category')} Breakdown")

    # Fallback
    if date_col and value_col:
        return _chart_monthly_trend(df, date_col, value_col, pal, layout)
    if (product_col or region_col) and value_col:
        dim = product_col or region_col
        return _chart_bar(df, dim, value_col, pal, layout, "Overview")

    return None, ""


# ── Chart helpers ──────────────────────────────────────────────────────────────

def _chart_monthly_trend(df, date_col, value_col, pal, layout):
    if not date_col or not value_col:
        return None, ""
    if date_col not in df.columns or value_col not in df.columns:
        return None, ""
    try:
        tmp = df[[date_col, value_col]].copy()
        tmp[date_col]  = pd.to_datetime(tmp[date_col], errors="coerce")
        tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
        tmp = tmp.dropna().set_index(date_col).sort_index()
        monthly = tmp[value_col].resample("ME").sum().reset_index()
        monthly.columns = ["period", "value"]
        monthly["period"] = monthly["period"].dt.strftime("%Y-%m")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=monthly["period"], y=monthly["value"],
            mode="lines+markers",
            line=dict(color=pal[0], width=2.5),
            marker=dict(size=7),
            fill="tozeroy",
            fillcolor="rgba(99,102,241,0.10)",
            name=_pretty(value_col),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f}<extra></extra>",
        ))
        fig.update_layout(
            xaxis_title="Month",
            yaxis_title=_pretty(value_col),
            **layout,
        )
        return fig, f"Monthly {_pretty(value_col)} Trend"
    except Exception:
        return None, ""


def _chart_bar(df, dim_col, value_col, pal, layout, title=""):
    if not dim_col or not value_col:
        return None, ""
    if dim_col not in df.columns or value_col not in df.columns:
        return None, ""
    try:
        tmp = df[[dim_col, value_col]].copy()
        tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
        grp = (
            tmp.groupby(dim_col)[value_col]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        fig = px.bar(
            grp, x=dim_col, y=value_col, color=dim_col,
            color_discrete_sequence=pal,
            labels={dim_col: _pretty(dim_col), value_col: _pretty(value_col)},
            text=value_col,
        )
        fig.update_traces(
            texttemplate="%{text:,.0f}", textposition="outside",
            hovertemplate=(
                f"<b>%{{x}}</b><br>{_pretty(value_col)}: %{{y:,.0f}}<extra></extra>"
            ),
        )
        fig.update_layout(showlegend=False, bargap=0.22, **layout)
        return fig, title or f"{_pretty(value_col)} by {_pretty(dim_col)}"
    except Exception:
        return None, ""


def _chart_histogram(df, value_col, pal, layout):
    if not value_col or value_col not in df.columns:
        return None, ""
    try:
        vals = pd.to_numeric(df[value_col], errors="coerce").dropna()
        fig = px.histogram(
            x=vals,
            nbins=25,
            color_discrete_sequence=pal,
            labels={"x": _pretty(value_col)},
        )
        fig.update_layout(**layout)
        return fig, f"Distribution of {_pretty(value_col)}"
    except Exception:
        return None, ""


def _chart_correlation(df, layout):
    try:
        num_cols = df.select_dtypes(include="number").columns.tolist()
        if len(num_cols) < 2:
            return None, ""
        corr = df[num_cols].corr()
        fig = px.imshow(
            corr, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
            text_auto=".2f", aspect="auto",
        )
        fig.update_layout(
            height=400,
            paper_bgcolor=layout.get("paper_bgcolor", "#111827"),
            plot_bgcolor=layout.get("plot_bgcolor", "#111827"),
            font=layout.get("font", {}),
        )
        return fig, "Correlation Heatmap"
    except Exception:
        return None, ""


def _chart_forecast(df, date_col, value_col, pal, layout):
    """Inline 3-period forecast using the project forecasting module."""
    if not date_col or not value_col:
        return None, ""
    if date_col not in df.columns or value_col not in df.columns:
        return None, ""
    try:
        from forecasting import run_forecast
        result = run_forecast(df, date_col, value_col, periods=3, method="auto")
        if result.error:
            return None, ""

        fig = go.Figure()
        if result.historical_df is not None and not result.historical_df.empty:
            hist = result.historical_df
            fig.add_trace(go.Scatter(
                x=hist["date"], y=hist["value"],
                mode="lines+markers", name="Historical",
                line=dict(color=pal[0], width=2.5),
                hovertemplate="<b>%{x|%Y-%m}</b><br>Actual: %{y:,.0f}<extra></extra>",
            ))
        if result.forecast_df is not None and not result.forecast_df.empty:
            fcast = result.forecast_df
            if "lower_ci" in fcast.columns:
                fig.add_trace(go.Scatter(
                    x=pd.concat([fcast["date"], fcast["date"].iloc[::-1]]),
                    y=pd.concat([fcast["upper_ci"], fcast["lower_ci"].iloc[::-1]]),
                    fill="toself", fillcolor="rgba(99,102,241,0.15)",
                    line=dict(color="rgba(99,102,241,0)"),
                    name="95% CI", hoverinfo="skip",
                ))
            fig.add_trace(go.Scatter(
                x=fcast["date"], y=fcast["predicted"],
                mode="lines+markers", name="Forecast",
                line=dict(
                    color=pal[1] if len(pal) > 1 else "#22C55E",
                    width=2.5, dash="dash"
                ),
                marker=dict(size=8, symbol="diamond"),
                hovertemplate="<b>%{x|%Y-%m}</b><br>Forecast: %{y:,.0f}<extra></extra>",
            ))
        fig.update_layout(
            xaxis_title="Month", yaxis_title=_pretty(value_col),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1),
            **layout,
        )
        return fig, f"Forecast -- Next 3 Periods ({_pretty(value_col)})"
    except Exception:
        return None, ""


# ── Main agent entry point ─────────────────────────────────────────────────────

def ask_agent(
    question:     str,
    df:           pd.DataFrame,
    col_map:      dict,
    chat_history: list | None = None,
    palette:      list | None = None,
    dark:         bool        = True,
) -> AgentResponse:
    """
    Conversational agent main entry point.

    Parameters
    ----------
    question     : user natural-language question
    df           : active DataFrame (uploaded or built-in)
    col_map      : {"date", "value", "product", "region"} column name map
    chat_history : list of {"role": "user"|"assistant", "content": str}
    palette      : Plotly color palette
    dark         : chart dark mode

    Returns
    -------
    AgentResponse with .answer, .fig, .chart_title, .reasoning, .intent
    """
    resp = AgentResponse(question=question)

    # 1. Detect intent
    intent      = detect_question_intent(question, col_map)
    resp.intent = intent["intent"]

    # 2. Build data context
    context = build_agent_context(df, col_map, intent)

    # 3. Build chart
    try:
        fig, chart_title = build_chart_from_intent(df, col_map, intent, palette, dark)
        resp.fig         = fig
        resp.chart_title = chart_title
    except Exception:
        resp.fig         = None
        resp.chart_title = ""

    # 4. Call LLM (non-blocking — fallback to stats if unavailable)
    try:
        llm_answer, reasoning = _call_llm(question, context, intent, chat_history or [])
        resp.answer    = llm_answer
        resp.reasoning = reasoning
    except Exception as exc:
        resp.answer    = _fallback_answer(question, df, col_map, intent)
        resp.reasoning = f"LLM unavailable: {exc}"

    return resp


# ── LLM caller ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert business data analyst AI embedded in a BI dashboard.
The user asks questions about their dataset. You receive a dataset context summary.

Your task:
- Answer the question directly using the data provided
- Quote specific numbers from the context when relevant
- For "why" questions: propose the most likely data-driven explanation
- Keep answers to 3-5 clear sentences
- Close with one concrete, actionable business recommendation
- Write in confident, professional prose -- no bullet points, no markdown headers

If the Groq API context data shows a decline, explain what period it occurred and the magnitude.
If asked to compare, rank all groups from highest to lowest."""


def _call_llm(
    question:     str,
    context:      str,
    intent:       dict,
    chat_history: list,
) -> tuple:
    """Returns (answer, reasoning) or raises on error."""
    try:
        from llm import get_groq_client
        client = get_groq_client()
    except Exception as exc:
        raise RuntimeError(f"Cannot connect to Groq: {exc}") from exc

    messages: list = [{"role": "system", "content": _SYSTEM_PROMPT}]

    # Include last 6 turns of history for continuity
    for turn in (chat_history or [])[-6:]:
        messages.append(turn)

    user_content = (
        f"Question: {question}\n\n"
        f"Dataset Context:\n{context}\n\n"
        f"Detected Intent: {intent.get('intent', 'general')}"
    )
    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model       = "llama-3.3-70b-versatile",
        messages    = messages,
        temperature = 0.3,
        max_tokens  = 400,
    )
    answer = response.choices[0].message.content.strip()
    return answer, ""


# ── Statistical fallback (no API key) ─────────────────────────────────────────

def _fallback_answer(question: str, df: pd.DataFrame, col_map: dict, intent: dict) -> str:
    """Generate a basic statistical answer without LLM."""
    value_col   = intent.get("value_col")
    product_col = intent.get("product_col")
    region_col  = intent.get("region_col")
    intent_key  = intent.get("intent", "general")

    if not value_col or value_col not in df.columns:
        return (
            "I can see your dataset but need a value/metric column to answer. "
            "Please set the column mapping above."
        )

    val_series = pd.to_numeric(df[value_col], errors="coerce").dropna()
    total      = val_series.sum()
    avg        = val_series.mean()

    if intent_key == "best_product" and product_col and product_col in df.columns:
        grp  = df.groupby(product_col)[value_col].sum().sort_values(ascending=False)
        best = grp.index[0]
        bval = grp.iloc[0]
        return (
            f"The best-performing product is **{best}** with total "
            f"{_pretty(value_col)} of {bval:,.0f}. "
            f"Dataset total: {total:,.0f}. "
            "Set your Groq API key for deeper AI analysis."
        )

    if intent_key == "compare_regions" and region_col and region_col in df.columns:
        grp  = df.groupby(region_col)[value_col].sum().sort_values(ascending=False)
        best = grp.index[0]
        bval = grp.iloc[0]
        return (
            f"The top region is **{best}** with {_pretty(value_col)} of {bval:,.0f}. "
            f"Dataset total: {total:,.0f}. "
            "Set your Groq API key for AI-generated insights."
        )

    return (
        f"Dataset summary -- {_pretty(value_col)}: "
        f"total = {total:,.0f}, average per row = {avg:,.2f}. "
        "Set your Groq API key in the sidebar for detailed AI analysis."
    )


# ── Utility ───────────────────────────────────────────────────────────────────

def _pretty(col: str) -> str:
    return col.replace("_", " ").title() if col else ""
