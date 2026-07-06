"""
analytics_agent.py
------------------
Self-contained analytics engine that operates on any pandas DataFrame.

All functions are pure (no Streamlit, no SQL, no file I/O) so they can be:
  - Unit-tested independently
  - Reused by recommendation_agent.py
  - Called from app.py with any DataFrame (existing dataset or uploaded file)

Public API:
  generate_analytics_report(df, column_map)   → AnalyticsReport dataclass
  trend_analysis(df, date_col, value_col)      → dict
  detect_outliers(df, numeric_cols)            → dict
  best_worst_products(df, product_col, value_col, n) → dict
  best_worst_regions(df, region_col, value_col, n)   → dict
  revenue_profit_analysis(df)                  → dict
  growth_calculations(df, date_col, value_col) → dict
  correlation_analysis(df, numeric_cols)       → dict
  generate_ai_business_insights(report, api_key) → str
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ── AnalyticsReport dataclass ─────────────────────────────────────────────────

@dataclass
class AnalyticsReport:
    """Unified container for all analytics results."""
    column_map:          dict                    = field(default_factory=dict)
    trend:               Optional[dict]          = None
    outliers:            Optional[dict]          = None
    best_worst_products: Optional[dict]          = None
    best_worst_regions:  Optional[dict]          = None
    revenue_profit:      Optional[dict]          = None
    growth:              Optional[dict]          = None
    correlation:         Optional[dict]          = None
    ai_insights:         str                     = ""
    errors:              dict[str, str]          = field(default_factory=dict)


# ── Master entry point ────────────────────────────────────────────────────────

def generate_analytics_report(
    df:         pd.DataFrame,
    column_map: dict,
) -> AnalyticsReport:
    """
    Run all analytics sub-modules on *df* and return a unified AnalyticsReport.

    column_map keys (all optional — missing keys skip the relevant analysis):
      "date"     → name of the datetime / date column
      "value"    → name of the primary numeric metric (e.g. total_revenue)
      "product"  → name of the product/category column
      "region"   → name of the region/geography column
      "profit"   → name of a profit column (if any)

    Returns
    -------
    AnalyticsReport with all fields populated (None if the sub-analysis
    could not run due to missing columns or too little data).
    """
    report = AnalyticsReport(column_map=column_map)
    col_types = _infer_types(df)

    date_col    = column_map.get("date")
    value_col   = column_map.get("value")
    product_col = column_map.get("product")
    region_col  = column_map.get("region")
    numeric_cols = col_types["numeric"]

    # ── Trend analysis ────────────────────────────────────────────────────────
    if date_col and value_col and date_col in df.columns and value_col in df.columns:
        try:
            report.trend = trend_analysis(df, date_col, value_col)
        except Exception as e:
            report.errors["trend"] = str(e)

    # ── Outlier detection ─────────────────────────────────────────────────────
    if numeric_cols:
        try:
            report.outliers = detect_outliers(df, numeric_cols)
        except Exception as e:
            report.errors["outliers"] = str(e)

    # ── Best / Worst products ─────────────────────────────────────────────────
    if product_col and value_col and product_col in df.columns and value_col in df.columns:
        try:
            report.best_worst_products = best_worst_products(df, product_col, value_col)
        except Exception as e:
            report.errors["best_worst_products"] = str(e)

    # ── Best / Worst regions ──────────────────────────────────────────────────
    if region_col and value_col and region_col in df.columns and value_col in df.columns:
        try:
            report.best_worst_regions = best_worst_regions(df, region_col, value_col)
        except Exception as e:
            report.errors["best_worst_regions"] = str(e)

    # ── Revenue & profit analysis ─────────────────────────────────────────────
    if value_col and value_col in df.columns:
        try:
            report.revenue_profit = revenue_profit_analysis(df, column_map)
        except Exception as e:
            report.errors["revenue_profit"] = str(e)

    # ── Growth calculations ───────────────────────────────────────────────────
    if date_col and value_col and date_col in df.columns and value_col in df.columns:
        try:
            report.growth = growth_calculations(df, date_col, value_col)
        except Exception as e:
            report.errors["growth"] = str(e)

    # ── Correlation analysis ──────────────────────────────────────────────────
    if len(numeric_cols) >= 2:
        try:
            report.correlation = correlation_analysis(df, numeric_cols)
        except Exception as e:
            report.errors["correlation"] = str(e)

    return report


# ── Trend analysis ────────────────────────────────────────────────────────────

def trend_analysis(
    df:        pd.DataFrame,
    date_col:  str,
    value_col: str,
    freq:      str = "ME",       # pandas offset alias (ME = month end)
) -> dict:
    """
    Aggregate *value_col* by calendar period and compute period-over-period
    change rates.

    Returns
    -------
    {
      "monthly": DataFrame (as records) with columns [period, value, pct_change],
      "overall_trend": "upward" | "downward" | "flat",
      "peak_period": str,
      "trough_period": str,
      "avg_monthly_growth_pct": float,
    }
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col, value_col])
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=[value_col])

    if df.empty:
        return {"monthly": [], "overall_trend": "flat",
                "peak_period": None, "trough_period": None,
                "avg_monthly_growth_pct": 0.0}

    df = df.set_index(date_col).sort_index()

    # Use period frequency — try ME (month-end, pandas ≥ 2.2) else MS
    try:
        monthly = df[value_col].resample(freq).sum()
    except Exception:
        monthly = df[value_col].resample("MS").sum()

    monthly = monthly[monthly > 0]
    if monthly.empty:
        return {"monthly": [], "overall_trend": "flat",
                "peak_period": None, "trough_period": None,
                "avg_monthly_growth_pct": 0.0}

    pct_change = monthly.pct_change().fillna(0) * 100

    records = []
    for period, val in monthly.items():
        records.append({
            "period":     str(period)[:7],   # YYYY-MM
            "value":      round(float(val), 2),
            "pct_change": round(float(pct_change.get(period, 0.0)), 2),
        })

    # Trend direction: compare first half avg vs second half avg
    n    = len(monthly)
    first_half  = float(monthly.iloc[:n//2].mean()) if n >= 2 else 0
    second_half = float(monthly.iloc[n//2:].mean()) if n >= 2 else 0

    if second_half > first_half * 1.05:
        overall_trend = "upward"
    elif second_half < first_half * 0.95:
        overall_trend = "downward"
    else:
        overall_trend = "flat"

    peak_period   = str(monthly.idxmax())[:7] if not monthly.empty else None
    trough_period = str(monthly.idxmin())[:7] if not monthly.empty else None

    avg_growth = float(pct_change.iloc[1:].mean()) if len(pct_change) > 1 else 0.0

    return {
        "monthly":                records,
        "overall_trend":          overall_trend,
        "peak_period":            peak_period,
        "trough_period":          trough_period,
        "avg_monthly_growth_pct": round(avg_growth, 2),
    }


# ── Outlier detection ─────────────────────────────────────────────────────────

def detect_outliers(
    df:           pd.DataFrame,
    numeric_cols: list[str],
    method:       str = "iqr",   # "iqr" | "zscore"
    zscore_thresh: float = 3.0,
    iqr_factor:    float = 1.5,
) -> dict:
    """
    Detect outliers in every numeric column using IQR or z-score method.

    Returns
    -------
    {
      col_name: {
        "method": str,
        "n_outliers": int,
        "outlier_pct": float,
        "lower_bound": float,
        "upper_bound": float,
        "sample_outliers": [float, ...],   # up to 5 extreme values
      },
      ...
    }
    """
    result: dict = {}

    for col in numeric_cols:
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 4:
            continue

        if method == "iqr":
            q1, q3 = float(series.quantile(0.25)), float(series.quantile(0.75))
            iqr    = q3 - q1
            lower  = q1 - iqr_factor * iqr
            upper  = q3 + iqr_factor * iqr
            mask   = (series < lower) | (series > upper)
        else:  # zscore
            mean   = float(series.mean())
            std    = float(series.std())
            lower  = mean - zscore_thresh * std
            upper  = mean + zscore_thresh * std
            mask   = ((series - mean) / (std + 1e-9)).abs() > zscore_thresh

        outlier_vals = series[mask]
        result[col] = {
            "method":          method,
            "n_outliers":      int(mask.sum()),
            "outlier_pct":     round(float(mask.mean()) * 100, 2),
            "lower_bound":     round(lower, 4),
            "upper_bound":     round(upper, 4),
            "sample_outliers": [round(v, 4) for v in
                                sorted(outlier_vals.abs(), reverse=True)[:5]],
        }

    return result


# ── Best / Worst products ─────────────────────────────────────────────────────

def best_worst_products(
    df:          pd.DataFrame,
    product_col: str,
    value_col:   str,
    n:           int = 5,
) -> dict:
    """
    Aggregate *value_col* by *product_col* and return the top-N and bottom-N.

    Returns
    -------
    {
      "best":  [{"label": str, "value": float, "rank": int}, ...],
      "worst": [{"label": str, "value": float, "rank": int}, ...],
      "total_groups": int,
    }
    """
    df = df.copy()
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    grouped = (
        df.groupby(product_col, sort=False)[value_col]
        .sum()
        .dropna()
        .sort_values(ascending=False)
    )
    if grouped.empty:
        return {"best": [], "worst": [], "total_groups": 0}

    def _to_list(series: pd.Series, reverse=False) -> list[dict]:
        items = series.head(n) if not reverse else series.tail(n).iloc[::-1]
        return [
            {"label": str(k), "value": round(float(v), 2), "rank": i + 1}
            for i, (k, v) in enumerate(items.items())
        ]

    return {
        "best":         _to_list(grouped),
        "worst":        _to_list(grouped, reverse=True),
        "total_groups": len(grouped),
    }


# ── Best / Worst regions ──────────────────────────────────────────────────────

def best_worst_regions(
    df:         pd.DataFrame,
    region_col: str,
    value_col:  str,
    n:          int = 5,
) -> dict:
    """Same signature and output shape as best_worst_products."""
    # Re-use the product function — same logic, different semantic label
    result = best_worst_products(df, region_col, value_col, n)
    return result


# ── Revenue & profit analysis ─────────────────────────────────────────────────

def revenue_profit_analysis(
    df:         pd.DataFrame,
    column_map: dict | None = None,
) -> dict:
    """
    Compute aggregate revenue and (if available) profit statistics.

    Returns
    -------
    {
      "total_revenue":   float,
      "avg_revenue":     float,
      "median_revenue":  float,
      "revenue_std":     float,
      "total_profit":    float | None,
      "avg_margin_pct":  float | None,
      "top_revenue_col": str,          # column used for revenue
    }
    """
    column_map = column_map or {}
    value_col  = column_map.get("value", "")
    profit_col = column_map.get("profit", "")

    result: dict = {
        "total_revenue":  None,
        "avg_revenue":    None,
        "median_revenue": None,
        "revenue_std":    None,
        "total_profit":   None,
        "avg_margin_pct": None,
        "top_revenue_col": value_col,
    }

    if value_col and value_col in df.columns:
        rev = pd.to_numeric(df[value_col], errors="coerce").dropna()
        result["total_revenue"]  = round(float(rev.sum()), 2)
        result["avg_revenue"]    = round(float(rev.mean()), 2)
        result["median_revenue"] = round(float(rev.median()), 2)
        result["revenue_std"]    = round(float(rev.std()), 2)

    if profit_col and profit_col in df.columns:
        profit = pd.to_numeric(df[profit_col], errors="coerce").dropna()
        result["total_profit"] = round(float(profit.sum()), 2)
        if result["total_revenue"] and result["total_revenue"] > 0:
            result["avg_margin_pct"] = round(
                result["total_profit"] / result["total_revenue"] * 100, 2
            )

    return result


# ── Growth calculations ───────────────────────────────────────────────────────

def growth_calculations(
    df:        pd.DataFrame,
    date_col:  str,
    value_col: str,
) -> dict:
    """
    Compute Month-over-Month (MoM) and Year-over-Year (YoY) growth rates.

    Returns
    -------
    {
      "mom": [{"period": str, "value": float, "growth_pct": float}, ...],
      "yoy": [{"year": str, "value": float, "growth_pct": float}, ...],
      "best_mom_growth":  {"period": str, "growth_pct": float} | None,
      "worst_mom_growth": {"period": str, "growth_pct": float} | None,
      "cagr_pct":         float | None,
    }
    """
    df = df.copy()
    df[date_col]  = pd.to_datetime(df[date_col], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=[date_col, value_col]).set_index(date_col).sort_index()

    if df.empty:
        return {"mom": [], "yoy": [], "best_mom_growth": None,
                "worst_mom_growth": None, "cagr_pct": None}

    # MoM
    try:
        monthly = df[value_col].resample("ME").sum()
    except Exception:
        monthly = df[value_col].resample("MS").sum()

    mom_pct = monthly.pct_change().fillna(0) * 100
    mom_records = [
        {
            "period":     str(p)[:7],
            "value":      round(float(v), 2),
            "growth_pct": round(float(mom_pct.get(p, 0.0)), 2),
        }
        for p, v in monthly.items()
    ]

    # YoY
    yearly    = df[value_col].resample("YE").sum()
    yoy_pct   = yearly.pct_change().fillna(0) * 100
    yoy_records = [
        {
            "year":       str(y)[:4],
            "value":      round(float(v), 2),
            "growth_pct": round(float(yoy_pct.get(y, 0.0)), 2),
        }
        for y, v in yearly.items()
    ]

    # Best / Worst MoM
    best_mom  = None
    worst_mom = None
    if len(mom_records) > 1:
        sorted_mom = sorted(mom_records[1:], key=lambda r: r["growth_pct"])
        worst_mom  = {"period": sorted_mom[0]["period"],
                      "growth_pct": sorted_mom[0]["growth_pct"]}
        best_mom   = {"period": sorted_mom[-1]["period"],
                      "growth_pct": sorted_mom[-1]["growth_pct"]}

    # CAGR
    cagr = None
    if len(yearly) >= 2:
        v_start = float(yearly.iloc[0])
        v_end   = float(yearly.iloc[-1])
        n_years = len(yearly) - 1
        if v_start > 0 and v_end > 0 and n_years > 0:
            cagr = round(((v_end / v_start) ** (1 / n_years) - 1) * 100, 2)

    return {
        "mom":              mom_records,
        "yoy":              yoy_records,
        "best_mom_growth":  best_mom,
        "worst_mom_growth": worst_mom,
        "cagr_pct":         cagr,
    }


# ── Correlation analysis ──────────────────────────────────────────────────────

def correlation_analysis(
    df:           pd.DataFrame,
    numeric_cols: list[str],
    method:       str = "pearson",
) -> dict:
    """
    Compute pairwise correlations for *numeric_cols*.

    Returns
    -------
    {
      "matrix":      dict-of-dicts  (col → col → r value),
      "strong_pairs": [{"col_a": str, "col_b": str, "r": float, "strength": str}, ...],
      "method":      str,
    }
    Strong pairs: |r| > 0.5, sorted by |r| descending.
    """
    valid_cols = [c for c in numeric_cols if c in df.columns]
    if len(valid_cols) < 2:
        return {"matrix": {}, "strong_pairs": [], "method": method}

    sub = df[valid_cols].copy()
    for c in valid_cols:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
    sub = sub.dropna()

    if len(sub) < 4:
        return {"matrix": {}, "strong_pairs": [], "method": method}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        corr = sub.corr(method=method)

    matrix = {
        col: {c2: round(float(v), 4) for c2, v in row.items()}
        for col, row in corr.to_dict().items()
    }

    # Extract strong unique pairs (upper triangle, |r| > 0.5, exclude self)
    strong: list[dict] = []
    cols = corr.columns.tolist()
    for i, ca in enumerate(cols):
        for cb in cols[i+1:]:
            r = float(corr.loc[ca, cb])
            if abs(r) >= 0.5:
                strength = (
                    "very strong" if abs(r) >= 0.8 else
                    "strong"      if abs(r) >= 0.65 else
                    "moderate"
                )
                strong.append({
                    "col_a":    ca,
                    "col_b":    cb,
                    "r":        round(r, 4),
                    "strength": strength,
                    "direction": "positive" if r > 0 else "negative",
                })
    strong.sort(key=lambda x: abs(x["r"]), reverse=True)

    return {
        "matrix":       matrix,
        "strong_pairs": strong,
        "method":       method,
    }


# ── AI business insights (LLM) ────────────────────────────────────────────────

def generate_ai_business_insights(
    report:  AnalyticsReport,
    df:      pd.DataFrame,
    api_key: str = "",
) -> str:
    """
    Call the Groq LLM (via the existing llm.get_groq_client()) to generate
    an executive-level business insight paragraph from the analytics report.

    Returns an empty string on any error (non-critical — never crashes the app).
    """
    try:
        import os
        if api_key:
            os.environ["GROQ_API_KEY"] = api_key
        from llm import get_groq_client
        client = get_groq_client()
    except Exception:
        return ""

    # Build a concise context from the report
    context_parts: list[str] = []

    if report.trend:
        t = report.trend
        context_parts.append(
            f"Trend: {t.get('overall_trend','N/A')} overall; "
            f"avg monthly growth {t.get('avg_monthly_growth_pct', 0):.1f}%; "
            f"peak at {t.get('peak_period','N/A')}, trough at {t.get('trough_period','N/A')}."
        )

    if report.best_worst_products:
        bwp = report.best_worst_products
        best  = bwp.get("best", [])
        worst = bwp.get("worst", [])
        if best:
            context_parts.append(
                "Top product: " + best[0]["label"] + f" (${best[0]['value']:,.0f})."
            )
        if worst:
            context_parts.append(
                "Bottom product: " + worst[0]["label"] + f" (${worst[0]['value']:,.0f})."
            )

    if report.best_worst_regions:
        bwr = report.best_worst_regions
        best  = bwr.get("best", [])
        worst = bwr.get("worst", [])
        if best:
            context_parts.append(
                "Top region: " + best[0]["label"] + f" (${best[0]['value']:,.0f})."
            )
        if worst:
            context_parts.append(
                "Bottom region: " + worst[0]["label"] + f" (${worst[0]['value']:,.0f})."
            )

    if report.revenue_profit:
        rp = report.revenue_profit
        if rp.get("total_revenue") is not None:
            context_parts.append(
                f"Total revenue: ${rp['total_revenue']:,.0f}; "
                f"avg per row: ${rp.get('avg_revenue', 0):,.2f}."
            )

    if report.growth:
        g  = report.growth
        bm = g.get("best_mom_growth")
        wm = g.get("worst_mom_growth")
        cagr = g.get("cagr_pct")
        if bm:
            context_parts.append(
                f"Best MoM growth: {bm['period']} (+{bm['growth_pct']:.1f}%)."
            )
        if wm:
            context_parts.append(
                f"Worst MoM: {wm['period']} ({wm['growth_pct']:.1f}%)."
            )
        if cagr is not None:
            context_parts.append(f"CAGR: {cagr:.1f}%.")

    if report.correlation and report.correlation.get("strong_pairs"):
        sp = report.correlation["strong_pairs"][0]
        context_parts.append(
            f"Strongest correlation: {sp['col_a']} ↔ {sp['col_b']} "
            f"(r={sp['r']}, {sp['strength']}, {sp['direction']})."
        )

    if not context_parts:
        return ""

    context = "\n".join(context_parts)

    system_msg = (
        "You are a senior business analyst. Write an executive summary of 4-6 sentences "
        "based on the analytics findings below. Be specific with numbers, highlight the "
        "most important finding first, and close with one clear strategic recommendation. "
        "Plain prose only — no bullet points, no markdown, no headers."
    )
    user_msg = f"Analytics findings:\n{context}"

    try:
        response = client.chat.completions.create(
            model       = "llama-3.3-70b-versatile",
            messages    = [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            temperature = 0.3,
            max_tokens  = 300,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[AnalyticsAgent] LLM insight skipped: {exc}")
        return ""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _infer_types(df: pd.DataFrame) -> dict[str, list[str]]:
    """Quick internal type sniffer (no import of ingestion.py to avoid circular deps)."""
    numeric:      list[str] = []
    categorical:  list[str] = []
    datetime_cols: list[str] = []
    for col in df.columns:
        dtype = df[col].dtype
        if pd.api.types.is_datetime64_any_dtype(dtype):
            datetime_cols.append(col)
        elif pd.api.types.is_numeric_dtype(dtype):
            numeric.append(col)
        else:
            # Try numeric coercion on a sample
            sample = df[col].dropna().head(200)
            if not sample.empty:
                coerced = pd.to_numeric(sample, errors="coerce")
                if coerced.notna().mean() >= 0.80:
                    numeric.append(col)
                    continue
            categorical.append(col)
    return {"numeric": numeric, "categorical": categorical, "datetime": datetime_cols}
