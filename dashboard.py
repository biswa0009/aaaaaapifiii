"""
dashboard.py
------------
Multi-chart dashboard generator.

Given one primary LLM result (df + meta), automatically generates
a full 4-panel dashboard:

  Panel 1 (primary)  — the chart the LLM recommended
  Panel 2 (companion)— pie / bar counterpart
  Panel 3 (trend)    — monthly revenue trend (always useful context)
  Panel 4 (table)    — sortable raw data view

Also provides drill-down SQL generation.
"""

from __future__ import annotations
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from database import run_query
from themes   import get_layout, get_palette


# ── Drill-down dimension map ──────────────────────────────────────────────────
# When user drills into a value of dimension X, show breakdown by dimension Y
_DRILLDOWN_MAP: dict[str, str] = {
    "customer_region"  : "product_category",
    "product_category" : "customer_region",
    "payment_method"   : "product_category",
    "order_date"       : "product_category",
    "month"            : "customer_region",
}


# ── Entry point ───────────────────────────────────────────────────────────────
def generate_dashboard(
    conn        : sqlite3.Connection,
    primary_df  : pd.DataFrame,
    primary_meta: dict,
    where_clause: str,        # from filters.get_where_clause()
    customization: dict,      # from sidebar customization panel
) -> list[dict]:
    """
    Returns a list of chart-panel dicts:
      { "title": str, "fig": go.Figure, "df": pd.DataFrame, "panel_id": str }
    """
    palette   = get_palette(customization.get("palette", "Bold"))
    dark      = customization.get("dark_mode", False)
    top_n     = customization.get("top_n", 0)       # 0 = no limit
    labels    = customization.get("show_labels", True)
    sort_asc  = customization.get("sort_asc", False)

    x_col = primary_meta["x_axis"]
    y_col = primary_meta["y_axis"]
    title = primary_meta.get("title", f"{_pretty(y_col)} by {_pretty(x_col)}")

    panels = []

    # ── Panel 1: Primary chart (LLM type) ────────────────────────────────────
    df1  = _trim(primary_df, y_col, top_n, sort_asc)
    fig1 = _build(df1, x_col, y_col, primary_meta["chart_type"],
                  palette, dark, title, labels)
    panels.append({"title": title, "fig": fig1, "df": df1, "panel_id": "primary"})

    # ── Panel 2: Companion pie (only for categorical X, ≥2 groups) ───────────
    is_categorical = (x_col != "order_date" and x_col != "month")
    if is_categorical and len(primary_df) >= 2:
        comp_type = "pie" if primary_meta["chart_type"] == "bar" else "bar"
        comp_title = f"Share by {_pretty(x_col)}" if comp_type == "pie" else f"{_pretty(y_col)} by {_pretty(x_col)}"
        fig2 = _build(df1, x_col, y_col, comp_type, palette, dark, comp_title, labels)
        panels.append({"title": comp_title, "fig": fig2, "df": df1, "panel_id": "companion"})

    # ── Panel 3: Monthly trend (only when primary is NOT already a trend) ─────
    if x_col not in ("order_date", "month"):
        where_fragment = f"WHERE {where_clause}" if where_clause else ""
        trend_sql = (
            f"SELECT strftime('%Y-%m', order_date) AS month, "
            f"SUM({y_col}) AS {y_col} "
            f"FROM sales {where_fragment} "
            f"GROUP BY month ORDER BY month"
        )
        trend_df, err = run_query(conn, trend_sql)
        if not err and trend_df is not None:
            trend_meta  = {**primary_meta, "chart_type": "line",
                           "x_axis": "month", "y_axis": y_col}
            trend_title = f"Monthly {_pretty(y_col)} Trend"
            fig3 = _build(trend_df, "month", y_col, "line",
                          palette, dark, trend_title, False)
            panels.append({"title": trend_title, "fig": fig3,
                           "df": trend_df, "panel_id": "trend"})

    return panels


# ── Drill-down SQL builder ────────────────────────────────────────────────────
def get_drilldown_sql(
    x_col          : str,
    selected_value : str,
    y_col          : str,
    extra_where    : str = "",   # from active filters
) -> tuple[str, str] | None:
    """
    Returns (sql, breakdown_col) for drilling into *selected_value* of *x_col*.
    Returns None if no drill-down mapping exists.
    """
    breakdown = _DRILLDOWN_MAP.get(x_col)
    if not breakdown:
        return None

    clauses = [f"{x_col} = '{_esc(selected_value)}'"]
    if extra_where:
        clauses.append(extra_where)
    where = " AND ".join(clauses)

    sql = (
        f"SELECT {breakdown}, SUM({y_col}) AS {y_col} "
        f"FROM sales "
        f"WHERE {where} "
        f"GROUP BY {breakdown} "
        f"ORDER BY {y_col} DESC"
    )
    return sql, breakdown


# ── Chart builder (all types) ─────────────────────────────────────────────────
def _build(
    df     : pd.DataFrame,
    x_col  : str,
    y_col  : str,
    ctype  : str,
    palette: list[str],
    dark   : bool,
    title  : str,
    labels : bool,
) -> go.Figure:
    df = df.copy()
    df[y_col] = pd.to_numeric(df[y_col], errors="coerce")
    layout    = get_layout(dark=dark, title=title)
    x_label   = _pretty(x_col)
    y_label   = _pretty(y_col)
    hover_tmpl = f"<b>%{{x}}</b><br>{y_label}: %{{y:,.2f}}<extra></extra>"

    # ── Bar ──────────────────────────────────────────────────────────────────
    if ctype == "bar":
        fig = px.bar(
            df, x=x_col, y=y_col, color=x_col,
            color_discrete_sequence=palette,
            labels={x_col: x_label, y_col: y_label},
            text=y_col if labels else None,
        )
        if labels:
            fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_traces(hovertemplate=hover_tmpl)
        fig.update_layout(showlegend=False, bargap=0.22, **layout)

    # ── Line ─────────────────────────────────────────────────────────────────
    elif ctype == "line":
        df = df.sort_values(by=x_col).reset_index(drop=True)
        fig = px.line(
            df, x=x_col, y=y_col, markers=True,
            color_discrete_sequence=palette,
            labels={x_col: x_label, y_col: y_label},
        )
        fig.update_traces(
            line_width=2.5, marker_size=8,
            hovertemplate=hover_tmpl,
            fill="tozeroy",
            fillcolor=f"rgba({_hex_to_rgb(palette[0])},0.12)",
        )
        fig.update_layout(**layout)

    # ── Pie / donut ───────────────────────────────────────────────────────────
    elif ctype == "pie":
        df = df.sort_values(by=y_col, ascending=False).reset_index(drop=True)
        fig = px.pie(
            df, names=x_col, values=y_col, hole=0.4,
            color_discrete_sequence=palette,
        )
        fig.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>%{value:,.2f} (%{percent})<extra></extra>",
            pull=[0.05] + [0] * (len(df) - 1),   # slight pull on top slice
        )
        pie_layout = {k: v for k, v in layout.items()
                      if k not in ("xaxis", "yaxis")}
        pie_layout["margin"] = dict(t=60, b=20, l=20, r=120)
        fig.update_layout(**pie_layout)

    # ── Area ──────────────────────────────────────────────────────────────────
    elif ctype == "area":
        df = df.sort_values(by=x_col).reset_index(drop=True)
        fig = px.area(
            df, x=x_col, y=y_col,
            color_discrete_sequence=palette,
            labels={x_col: x_label, y_col: y_label},
        )
        fig.update_traces(hovertemplate=hover_tmpl)
        fig.update_layout(**layout)

    # ── Scatter ───────────────────────────────────────────────────────────────
    elif ctype == "scatter":
        fig = px.scatter(
            df, x=x_col, y=y_col, color=x_col,
            color_discrete_sequence=palette,
            labels={x_col: x_label, y_col: y_label},
            size=y_col, size_max=50,
        )
        fig.update_traces(hovertemplate=hover_tmpl)
        fig.update_layout(**layout)

    # ── Histogram ─────────────────────────────────────────────────────────────
    elif ctype == "histogram":
        fig = px.histogram(
            df, x=y_col,
            color_discrete_sequence=palette,
            labels={y_col: y_label},
            nbins=20,
        )
        fig.update_layout(**layout)

    # ── Fallback → bar ────────────────────────────────────────────────────────
    else:
        return _build(df, x_col, y_col, "bar", palette, dark, title, labels)

    return fig


# ── Helpers ───────────────────────────────────────────────────────────────────
def _trim(df: pd.DataFrame, y_col: str, top_n: int, sort_asc: bool) -> pd.DataFrame:
    """Sort and optionally limit rows."""
    if y_col in df.columns:
        df = df.sort_values(by=y_col, ascending=sort_asc).reset_index(drop=True)
    if top_n and top_n < len(df):
        df = df.head(top_n)
    return df


def _pretty(col: str) -> str:
    return col.replace("_", " ").title()


def _esc(s: str) -> str:
    return str(s).replace("'", "''")


def _hex_to_rgb(hex_color: str) -> str:
    """Convert #RRGGBB to 'R,G,B' for rgba() strings."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r},{g},{b}"
    return "102,126,234"   # fallback purple
