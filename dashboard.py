"""
dashboard.py
------------
Multi-chart dashboard generator.

Original:
  generate_dashboard(conn, primary_df, primary_meta, where_clause, customization)
  → 4-panel dashboard from LLM result + SQL

New (v7):
  generate_adaptive_dashboard(df, col_map, customization)
  → Auto-generates ALL chart types from any DataFrame (no SQL, no LLM)
    Panels: KPI cards, line, bar, pie, scatter, histogram, treemap,
            correlation heatmap, geo map (when location column detected)

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
# Only TRUE categorical columns that exist as real table columns.
# Time-derived aliases (month, year, order_date) are excluded — their
# aggregated values ("2022-01") don't match raw order_date rows directly.
_DRILLDOWN_MAP: dict[str, str] = {
    "customer_region" : "product_category",
    "product_category": "customer_region",
    "payment_method"  : "product_category",
}
_TIME_COLS = {"order_date", "month", "year", "week", "quarter", "date"}


def can_drilldown(x_col: str) -> bool:
    """Return True only when x_col has a valid categorical drill-down path."""
    if x_col.lower() in _TIME_COLS:
        return False
    return x_col in _DRILLDOWN_MAP


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
    layout    = get_layout(dark=dark, title="")
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


# ══════════════════════════════════════════════════════════════════════════════
# ADAPTIVE DASHBOARD (v7) — works on any DataFrame, no SQL required
# ══════════════════════════════════════════════════════════════════════════════

# Column-name hints for geo detection
_GEO_KEYWORDS = {"country", "nation", "geo", "geography", "territory"}
_LOC_KEYWORDS = {"country", "nation", "geo", "geography", "territory",
                  "region", "state", "province", "city"}


def generate_adaptive_dashboard(
    df:            pd.DataFrame,
    col_map:       dict,
    customization: dict,
) -> list[dict]:
    """
    Auto-generate ALL chart types from any DataFrame.

    Parameters
    ----------
    df           : any pandas DataFrame (uploaded or built-in)
    col_map      : {"date", "value", "product", "region"} column name map
    customization: sidebar customization dict (palette, dark_mode, top_n, ...)

    Returns
    -------
    list of panel dicts: {"title", "fig", "panel_id", "chart_type"}
    """
    from ingestion import detect_column_types

    palette  = get_palette(customization.get("palette", "BI"))
    dark     = customization.get("dark_mode", True)
    top_n    = customization.get("top_n", 0)
    labels   = customization.get("show_labels", True)
    sort_asc = customization.get("sort_asc", False)

    layout = get_layout(dark=dark, title="")

    date_col    = col_map.get("date")
    value_col   = col_map.get("value")
    product_col = col_map.get("product")
    region_col  = col_map.get("region")

    col_types    = detect_column_types(df)
    numeric_cols = col_types["numeric"]
    cat_cols     = col_types["categorical"]

    panels: list[dict] = []

    # ── 1. KPI Cards (returned separately as metrics dict) ────────────────────
    kpis = _build_kpi_metrics(df, value_col, numeric_cols)
    panels.append({
        "title":      "Key Performance Indicators",
        "fig":        None,   # rendered as st.metric, not plotly
        "panel_id":   "kpi",
        "chart_type": "kpi",
        "kpis":       kpis,
    })

    # ── 2. Line Chart — monthly trend ─────────────────────────────────────────
    if date_col and value_col and date_col in df.columns and value_col in df.columns:
        fig_line = _adp_line(df, date_col, value_col, palette, dark, layout)
        if fig_line:
            panels.append({
                "title":      f"Monthly {_pretty(value_col)} Trend",
                "fig":        fig_line,
                "panel_id":   "line",
                "chart_type": "line",
            })

    # ── 3. Bar Chart — top categories ─────────────────────────────────────────
    bar_dim = product_col or (cat_cols[0] if cat_cols else None)
    if bar_dim and value_col and bar_dim in df.columns and value_col in df.columns:
        fig_bar = _adp_bar(df, bar_dim, value_col, palette, dark, layout, labels, top_n, sort_asc)
        if fig_bar:
            panels.append({
                "title":      f"{_pretty(value_col)} by {_pretty(bar_dim)}",
                "fig":        fig_bar,
                "panel_id":   "bar",
                "chart_type": "bar",
            })

    # ── 4. Pie Chart — share breakdown ────────────────────────────────────────
    pie_dim = product_col or (cat_cols[0] if cat_cols else None)
    if pie_dim and value_col and pie_dim in df.columns and value_col in df.columns:
        grp = df.groupby(pie_dim)[value_col].sum()
        n_groups = len(grp)
        if 2 <= n_groups <= 12:   # pie charts with too many slices are unreadable
            fig_pie = _adp_pie(df, pie_dim, value_col, palette, dark, layout)
            if fig_pie:
                panels.append({
                    "title":      f"Revenue Share by {_pretty(pie_dim)}",
                    "fig":        fig_pie,
                    "panel_id":   "pie",
                    "chart_type": "pie",
                })

    # ── 5. Scatter Plot — two numeric columns ─────────────────────────────────
    if len(numeric_cols) >= 2:
        x_num = numeric_cols[0]
        y_num = value_col if value_col and value_col in numeric_cols else numeric_cols[1]
        color_col = product_col or region_col or (cat_cols[0] if cat_cols else None)
        fig_scatter = _adp_scatter(df, x_num, y_num, color_col, palette, dark, layout)
        if fig_scatter:
            panels.append({
                "title":      f"{_pretty(x_num)} vs {_pretty(y_num)}",
                "fig":        fig_scatter,
                "panel_id":   "scatter",
                "chart_type": "scatter",
            })

    # ── 6. Histogram — value distribution ────────────────────────────────────
    hist_col = value_col or (numeric_cols[0] if numeric_cols else None)
    if hist_col and hist_col in df.columns:
        fig_hist = _adp_histogram(df, hist_col, palette, dark, layout)
        if fig_hist:
            panels.append({
                "title":      f"Distribution of {_pretty(hist_col)}",
                "fig":        fig_hist,
                "panel_id":   "histogram",
                "chart_type": "histogram",
            })

    # ── 7. Treemap — hierarchical breakdown ───────────────────────────────────
    if len(cat_cols) >= 2 and value_col and value_col in df.columns:
        fig_tree = _adp_treemap(df, cat_cols[:2], value_col, palette, dark)
        if fig_tree:
            panels.append({
                "title":      f"Treemap — {_pretty(cat_cols[0])} / {_pretty(cat_cols[1])}",
                "fig":        fig_tree,
                "panel_id":   "treemap",
                "chart_type": "treemap",
            })
    elif len(cat_cols) == 1 and value_col and value_col in df.columns:
        fig_tree = _adp_treemap(df, cat_cols[:1], value_col, palette, dark)
        if fig_tree:
            panels.append({
                "title":      f"Treemap — {_pretty(cat_cols[0])}",
                "fig":        fig_tree,
                "panel_id":   "treemap",
                "chart_type": "treemap",
            })

    # ── 8. Correlation Heatmap ────────────────────────────────────────────────
    if len(numeric_cols) >= 2:
        fig_corr = _adp_correlation(df, numeric_cols, dark)
        if fig_corr:
            panels.append({
                "title":      "Correlation Matrix",
                "fig":        fig_corr,
                "panel_id":   "correlation",
                "chart_type": "heatmap",
            })

    # ── 9. Region Bar Chart (second categorical) ──────────────────────────────
    if region_col and region_col != bar_dim and value_col and region_col in df.columns:
        fig_reg = _adp_bar(df, region_col, value_col, palette, dark, layout, labels, top_n, sort_asc)
        if fig_reg:
            panels.append({
                "title":      f"{_pretty(value_col)} by {_pretty(region_col)}",
                "fig":        fig_reg,
                "panel_id":   "region_bar",
                "chart_type": "bar",
            })

    # ── 10. Geo Map — choropleth when country/geo column detected ─────────────
    geo_col = _detect_geo_column(df)
    if geo_col and value_col and value_col in df.columns:
        fig_geo = _adp_geo(df, geo_col, value_col, dark)
        if fig_geo:
            panels.append({
                "title":      f"Geo Map — {_pretty(value_col)} by {_pretty(geo_col)}",
                "fig":        fig_geo,
                "panel_id":   "geo",
                "chart_type": "geo",
            })

    return panels


# ── Adaptive chart helpers ────────────────────────────────────────────────────

def _build_kpi_metrics(df: pd.DataFrame, value_col: str | None, numeric_cols: list) -> dict:
    """Return dict of KPI label → formatted value string."""
    kpis: dict = {}
    if not df.empty:
        kpis["Total Rows"] = f"{len(df):,}"
        kpis["Columns"]    = str(len(df.columns))

    if value_col and value_col in df.columns:
        v = pd.to_numeric(df[value_col], errors="coerce").dropna()
        if not v.empty:
            kpis[f"Total {_pretty(value_col)}"] = f"{v.sum():,.0f}"
            kpis[f"Avg {_pretty(value_col)}"]   = f"{v.mean():,.2f}"
            kpis[f"Max {_pretty(value_col)}"]   = f"{v.max():,.0f}"
            kpis[f"Min {_pretty(value_col)}"]   = f"{v.min():,.0f}"

    # Additional numeric KPIs (up to 2 extra cols)
    extra = [c for c in numeric_cols if c != value_col][:2]
    for col in extra:
        v2 = pd.to_numeric(df[col], errors="coerce").dropna()
        if not v2.empty:
            kpis[f"Avg {_pretty(col)}"] = f"{v2.mean():,.2f}"

    return kpis


def _adp_line(df, date_col, value_col, palette, dark, layout) -> go.Figure | None:
    try:
        tmp = df[[date_col, value_col]].copy()
        tmp[date_col]  = pd.to_datetime(tmp[date_col], errors="coerce")
        tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
        tmp = tmp.dropna().set_index(date_col).sort_index()
        monthly = tmp[value_col].resample("ME").sum().reset_index()
        monthly.columns = ["period", "value"]
        monthly["period_str"] = monthly["period"].dt.strftime("%Y-%m")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=monthly["period_str"], y=monthly["value"],
            mode="lines+markers",
            line=dict(color=palette[0], width=2.5),
            marker=dict(size=7),
            fill="tozeroy",
            fillcolor=f"rgba({_hex_to_rgb(palette[0])},0.12)",
            name=_pretty(value_col),
            hovertemplate="<b>%{x}</b><br>" + _pretty(value_col) + ": %{y:,.0f}<extra></extra>",
        ))
        fig.update_layout(xaxis_title="Month", yaxis_title=_pretty(value_col), **layout)
        return fig
    except Exception:
        return None


def _adp_bar(df, dim_col, value_col, palette, dark, layout, labels, top_n, sort_asc) -> go.Figure | None:
    try:
        tmp = df[[dim_col, value_col]].copy()
        tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
        grp = tmp.groupby(dim_col)[value_col].sum().sort_values(ascending=sort_asc).reset_index()
        if top_n and top_n < len(grp):
            grp = grp.tail(top_n) if sort_asc else grp.head(top_n)
        fig = px.bar(
            grp, x=dim_col, y=value_col, color=dim_col,
            color_discrete_sequence=palette,
            labels={dim_col: _pretty(dim_col), value_col: _pretty(value_col)},
            text=value_col if labels else None,
        )
        if labels:
            fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_traces(
            hovertemplate=f"<b>%{{x}}</b><br>{_pretty(value_col)}: %{{y:,.0f}}<extra></extra>"
        )
        fig.update_layout(showlegend=False, bargap=0.22, **layout)
        return fig
    except Exception:
        return None


def _adp_pie(df, dim_col, value_col, palette, dark, layout) -> go.Figure | None:
    try:
        tmp = df[[dim_col, value_col]].copy()
        tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
        grp = tmp.groupby(dim_col)[value_col].sum().sort_values(ascending=False).reset_index()
        fig = px.pie(
            grp, names=dim_col, values=value_col, hole=0.42,
            color_discrete_sequence=palette,
        )
        fig.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>%{value:,.0f} (%{percent})<extra></extra>",
            pull=[0.05] + [0] * (len(grp) - 1),
        )
        pie_layout = {k: v for k, v in layout.items() if k not in ("xaxis", "yaxis")}
        pie_layout["margin"] = dict(t=60, b=20, l=20, r=120)
        fig.update_layout(**pie_layout)
        return fig
    except Exception:
        return None


def _adp_scatter(df, x_col, y_col, color_col, palette, dark, layout) -> go.Figure | None:
    try:
        cols = [c for c in [x_col, y_col, color_col] if c and c in df.columns]
        tmp = df[cols].copy()
        for c in [x_col, y_col]:
            tmp[c] = pd.to_numeric(tmp[c], errors="coerce")
        tmp = tmp.dropna(subset=[x_col, y_col])
        if tmp.empty:
            return None

        kwargs: dict = dict(
            data_frame=tmp, x=x_col, y=y_col,
            color_discrete_sequence=palette,
            labels={x_col: _pretty(x_col), y_col: _pretty(y_col)},
            opacity=0.72,
        )
        if color_col and color_col in tmp.columns:
            kwargs["color"] = color_col

        fig = px.scatter(**kwargs)
        fig.update_traces(
            hovertemplate=(
                f"<b>{_pretty(x_col)}:</b> %{{x:,.2f}}<br>"
                f"<b>{_pretty(y_col)}:</b> %{{y:,.2f}}<extra></extra>"
            )
        )
        fig.update_layout(**layout)
        return fig
    except Exception:
        return None


def _adp_histogram(df, value_col, palette, dark, layout) -> go.Figure | None:
    try:
        vals = pd.to_numeric(df[value_col], errors="coerce").dropna()
        if vals.empty:
            return None
        fig = px.histogram(
            x=vals, nbins=30,
            color_discrete_sequence=[palette[0]],
            labels={"x": _pretty(value_col)},
        )
        fig.update_traces(
            hovertemplate=f"<b>{_pretty(value_col)} range:</b> %{{x}}<br>Count: %{{y}}<extra></extra>"
        )
        fig.update_layout(**layout)
        return fig
    except Exception:
        return None


def _adp_treemap(df, cat_cols, value_col, palette, dark) -> go.Figure | None:
    try:
        cols = cat_cols + [value_col]
        cols = [c for c in cols if c in df.columns]
        if not cols:
            return None
        tmp = df[cols].copy()
        tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce").fillna(0)
        tmp = tmp[tmp[value_col] > 0]
        if tmp.empty:
            return None

        # Build path from available cat cols
        path = [px.Constant("All")] + [c for c in cat_cols if c in tmp.columns]

        fig = px.treemap(
            tmp, path=path, values=value_col,
            color=value_col,
            color_continuous_scale="Blues",
        )
        fig.update_traces(
            hovertemplate="<b>%{label}</b><br>" + _pretty(value_col) + ": %{value:,.0f}<extra></extra>",
            textinfo="label+value",
        )
        bg = "#111827" if dark else "#FFFFFF"
        txt = "#E5E7EB" if dark else "#1F2937"
        fig.update_layout(
            paper_bgcolor=bg,
            font=dict(family="Inter, sans-serif", color=txt, size=12),
            margin=dict(l=10, r=10, t=40, b=10),
            height=400,
        )
        return fig
    except Exception:
        return None


def _adp_correlation(df, numeric_cols, dark) -> go.Figure | None:
    try:
        valid = [c for c in numeric_cols if c in df.columns]
        if len(valid) < 2:
            return None
        sub = df[valid].copy()
        for c in valid:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        sub = sub.dropna()
        if len(sub) < 4:
            return None

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            corr = sub.corr()

        fig = px.imshow(
            corr,
            color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1,
            text_auto=".2f",
            aspect="auto",
        )
        bg  = "#111827" if dark else "#FFFFFF"
        txt = "#E5E7EB" if dark else "#1F2937"
        fig.update_layout(
            height=max(350, len(valid) * 55),
            paper_bgcolor=bg,
            plot_bgcolor=bg,
            font=dict(family="Inter, sans-serif", color=txt, size=11),
            margin=dict(l=10, r=10, t=40, b=10),
            coloraxis_colorbar=dict(tickfont=dict(color=txt)),
        )
        return fig
    except Exception:
        return None


def _adp_geo(df, geo_col, value_col, dark) -> go.Figure | None:
    """Choropleth map when geo column holds recognisable country names or ISO codes."""
    try:
        tmp = df[[geo_col, value_col]].copy()
        tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
        grp = tmp.groupby(geo_col)[value_col].sum().reset_index()
        grp = grp.dropna()
        if grp.empty:
            return None

        # Heuristic: check if values look like ISO-3166 alpha-2/alpha-3 or country names
        sample = grp[geo_col].dropna().astype(str).head(20)
        is_iso2  = sample.str.len().eq(2).mean() >= 0.7
        is_iso3  = sample.str.len().eq(3).mean() >= 0.7

        if is_iso2:
            locationmode = "ISO-3"   # px will try to match anyway
        elif is_iso3:
            locationmode = "ISO-3"
        else:
            locationmode = "country names"

        bg  = "#111827" if dark else "#FFFFFF"
        txt = "#E5E7EB" if dark else "#1F2937"

        fig = px.choropleth(
            grp,
            locations=geo_col,
            locationmode=locationmode,
            color=value_col,
            color_continuous_scale="Blues",
            labels={value_col: _pretty(value_col)},
        )
        fig.update_layout(
            paper_bgcolor=bg,
            geo=dict(
                bgcolor=bg,
                showframe=False,
                showcoastlines=True,
                coastlinecolor="rgba(255,255,255,0.2)" if dark else "rgba(0,0,0,0.2)",
                landcolor="#1F2937" if dark else "#E5E7EB",
                oceancolor=bg,
                showocean=True,
                showlakes=False,
            ),
            font=dict(family="Inter, sans-serif", color=txt, size=12),
            margin=dict(l=0, r=0, t=40, b=10),
            height=420,
            coloraxis_colorbar=dict(tickfont=dict(color=txt)),
        )
        return fig
    except Exception:
        return None


def _detect_geo_column(df: pd.DataFrame) -> str | None:
    """Return the first column that looks like a geography column."""
    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in _GEO_KEYWORDS):
            # Check uniqueness: geo cols shouldn't have too many unique values
            n_unique = df[col].nunique()
            if 2 <= n_unique <= 250:
                return col
    return None

