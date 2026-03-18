"""
anomaly.py
----------
Z-score based anomaly detection for BI chart data.
Surfaces unusual data points that deviate significantly from the mean.
Called after every successful query — results shown in a warning panel.
"""

import pandas as pd


def detect_anomalies(
    df         : pd.DataFrame,
    y_col      : str,
    x_col      : str,
    threshold  : float = 2.0,
    max_results: int   = 3,
) -> list[dict]:
    """
    Detect statistical anomalies using the z-score method.

    Parameters
    ----------
    df          : query result DataFrame
    y_col       : numeric metric column
    x_col       : label / dimension column
    threshold   : z-score cutoff (default 2.0 ≈ top/bottom ~5%)
    max_results : cap on returned anomalies

    Returns
    -------
    List of dicts  { label, value, z_score, direction, pct_vs_mean }
    Empty list when there are fewer than 3 rows or no anomalies found.
    """
    if y_col not in df.columns or len(df) < 3:
        return []

    series = pd.to_numeric(df[y_col], errors="coerce").dropna()
    if len(series) < 3:
        return []

    mean = float(series.mean())
    std  = float(series.std())
    if std < 1e-9:          # constant data — nothing to flag
        return []

    anomalies = []
    for _, row in df.iterrows():
        val = pd.to_numeric(row.get(y_col, None), errors="coerce")
        if pd.isna(val):
            continue
        z = (float(val) - mean) / std
        if abs(z) < threshold:
            continue
        pct = ((float(val) - mean) / abs(mean) * 100) if mean != 0 else 0.0
        anomalies.append({
            "label"      : str(row.get(x_col, "")),
            "value"      : float(val),
            "z_score"    : round(z, 2),
            "direction"  : "above" if z > 0 else "below",
            "pct_vs_mean": round(pct, 1),
        })

    anomalies.sort(key=lambda a: abs(a["z_score"]), reverse=True)
    return anomalies[:max_results]


def format_anomaly_html(a: dict, y_col: str) -> str:
    """Return an HTML string describing one anomaly for display."""
    y_label   = y_col.replace("_", " ").title()
    icon      = ":material/trending_up:" if a["direction"] == "above" else ":material/trending_down:"
    sign      = "+" if a["pct_vs_mean"] >= 0 else ""
    color     = "var(--primary)" if a["direction"] == "above" else "var(--info)"
    return (
        f'<span style="color:{color}; font-size:18px; vertical-align:middle">{icon}</span> '
        f'<strong>{a["label"]}</strong> — {y_label}: '
        f'<strong>{a["value"]:,.0f}</strong> &nbsp;'
        f'<span style="color:var(--text-dim); font-size:11px">'
        f'({sign}{a["pct_vs_mean"]}% vs avg · z={a["z_score"]})</span>'
    )


def get_followup_suggestions(x_col: str, y_col: str) -> list[tuple[str, str]]:
    """
    Return 3 context-aware follow-up query suggestions as (icon, query) pairs.
    Used to populate the 'Explore Further' chip row below charts.
    """
    y = y_col.replace("_", " ")

    MAP = {
        "customer_region": [
            (":material/calendar_today:", f"monthly {y} trend by region"),
            (":material/inventory_2:", "product category breakdown by region"),
            (":material/payments:", "payment method preference by region"),
        ],
        "product_category": [
            (":material/monitoring:", f"monthly trend for each product category"),
            (":material/public:", "which region buys each category the most"),
            (":material/star:", "average rating comparison by product category"),
        ],
        "payment_type": [
            (":material/bar_chart:", f"{y} by product category per payment method"),
            (":material/show_chart:", "monthly payment method trend"),
            (":material/language:", "payment method distribution by region"),
        ],
        "month": [
            (":material/analytics:", f"which category drove the most {y} this year"),
            (":material/explore:", "compare regional performance by month"),
            (":material/wallet:", "payment method trends over time"),
        ],
        "order_date": [
            (":material/calendar_month:", f"monthly {y} aggregated by month"),
            (":material/leaderboard:", "category performance over time"),
            (":material/hub:", "regional revenue growth over time"),
        ],
    }
    default = [
        (":material/search:", f"compare {x_col.replace('_',' ')} performance by region"),
        (":material/show_chart:", f"monthly trend of {y}"),
        (":material/workspace_premium:", f"top 5 by {y}"),
    ]
    return MAP.get(x_col, default)
