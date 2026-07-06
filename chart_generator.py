"""
chart_generator.py  (v4)
------------------------
Thin wrapper — delegates to dashboard._build() so the same rendering
logic is used whether called from app.py directly or from dashboard.py.

Public API (unchanged from v3):
  build_chart(df, chart_meta, override_type=None) -> go.Figure
  get_summary_stats(df, y_col)                    -> dict
"""

import pandas as pd
import plotly.graph_objects as go

from themes    import get_palette
from dashboard import _build


def build_chart(
    df            : pd.DataFrame,
    chart_meta    : dict,
    override_type : str | None = None,
    customization : dict | None = None,
) -> go.Figure:
    """
    Build a single Plotly figure.
    customization keys: palette, dark_mode, show_labels, sort_asc, top_n
    """
    cust     = customization or {}
    ctype    = (override_type or chart_meta.get("chart_type", "bar")).lower()
    x_col    = chart_meta.get("x_axis", "")
    y_col    = chart_meta.get("y_axis", "")
    title    = chart_meta.get("title", "")
    palette  = get_palette(cust.get("palette", "Bold"))
    dark     = cust.get("dark_mode", False)
    labels   = cust.get("show_labels", True)
    sort_asc = cust.get("sort_asc", False)
    top_n    = cust.get("top_n", 0)

    _validate_columns(df, x_col, y_col)

    from dashboard import _trim
    df = _trim(df.copy(), y_col, top_n, sort_asc)

    return _build(df, x_col, y_col, ctype, palette, dark, title, labels)


def get_summary_stats(df: pd.DataFrame, y_col: str) -> dict:
    if y_col not in df.columns:
        return {}
    s = pd.to_numeric(df[y_col], errors="coerce").dropna()
    if s.empty:
        return {}
    return {
        "Total"  : f"{s.sum():,.2f}",
        "Average": f"{s.mean():,.2f}",
        "Max"    : f"{s.max():,.2f}",
        "Min"    : f"{s.min():,.2f}",
        "Rows"   : str(len(df)),
    }


def _validate_columns(df: pd.DataFrame, x_col: str, y_col: str) -> None:
    missing = [c for c in [x_col, y_col] if c not in df.columns]
    if missing:
        raise ValueError(
            f"Column(s) {missing} not found. Available: {list(df.columns)}"
        )
