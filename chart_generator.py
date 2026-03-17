"""
chart_generator.py
------------------
Converts a pandas DataFrame + chart metadata (from the LLM) into
a Plotly Figure ready to be rendered by Streamlit.

Supported chart types: bar, line, pie
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Colour palette (consistent across charts) ─────────────────────────────────
PALETTE = px.colors.qualitative.Bold


# ── Public entry point ────────────────────────────────────────────────────────
def build_chart(df: pd.DataFrame, chart_meta: dict) -> go.Figure:
    """
    Parameters
    ----------
    df          : DataFrame returned by database.run_query()
    chart_meta  : dict with keys  chart_type, x_axis, y_axis
                  (as returned by llm.ask_groq)

    Returns
    -------
    plotly.graph_objects.Figure

    Raises
    ------
    ValueError  if required columns are not present in df or chart type unknown
    """
    chart_type = chart_meta.get("chart_type", "bar").lower()
    x_col      = chart_meta.get("x_axis", "")
    y_col      = chart_meta.get("y_axis", "")

    # ── Column presence check ─────────────────────────────────────────────────
    _validate_columns(df, x_col, y_col)

    # ── Coerce numeric Y column ───────────────────────────────────────────────
    df = df.copy()
    df[y_col] = pd.to_numeric(df[y_col], errors="coerce")

    # ── Route to builder ──────────────────────────────────────────────────────
    builders = {
        "bar":  _build_bar,
        "line": _build_line,
        "pie":  _build_pie,
    }

    builder = builders.get(chart_type)
    if builder is None:
        # Unknown type → fall back to bar
        print(f"[Chart] Unknown chart type '{chart_type}' – falling back to bar.")
        builder = _build_bar

    fig = builder(df, x_col, y_col)
    _apply_common_layout(fig)
    return fig


# ── Chart builders ────────────────────────────────────────────────────────────
def _build_bar(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    """Grouped / single bar chart for category comparisons."""
    fig = px.bar(
        df,
        x            = x_col,
        y            = y_col,
        color        = x_col,
        color_discrete_sequence = PALETTE,
        text_auto    = ".3s",
        labels       = {x_col: _pretty(x_col), y_col: _pretty(y_col)},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False)
    return fig


def _build_line(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    """Line / area chart for time-series or ordered data."""
    # Sort by X so the line makes sense
    df = df.sort_values(by=x_col).reset_index(drop=True)

    fig = px.line(
        df,
        x      = x_col,
        y      = y_col,
        markers= True,
        labels = {x_col: _pretty(x_col), y_col: _pretty(y_col)},
        color_discrete_sequence = PALETTE,
    )
    fig.update_traces(line_width=2.5, marker_size=7)
    return fig


def _build_pie(df: pd.DataFrame, x_col: str, y_col: str) -> go.Figure:
    """Pie chart for part-to-whole comparisons."""
    fig = px.pie(
        df,
        names  = x_col,
        values = y_col,
        color_discrete_sequence = PALETTE,
        hole   = 0.35,          # Donut style – easier to read labels
    )
    fig.update_traces(
        textposition = "inside",
        textinfo     = "percent+label",
    )
    return fig


# ── Layout / styling ──────────────────────────────────────────────────────────
def _apply_common_layout(fig: go.Figure) -> None:
    """Apply a clean, professional layout to any figure."""
    fig.update_layout(
        font          = dict(family="Inter, sans-serif", size=13),
        plot_bgcolor  = "rgba(0,0,0,0)",
        paper_bgcolor = "rgba(0,0,0,0)",
        margin        = dict(t=40, b=60, l=60, r=40),
        xaxis         = dict(showgrid=False, tickangle=-30),
        yaxis         = dict(showgrid=True, gridcolor="rgba(200,200,200,0.3)"),
        hoverlabel    = dict(bgcolor="#1E1E2E", font_color="white"),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────
def _validate_columns(df: pd.DataFrame, x_col: str, y_col: str) -> None:
    """Raise ValueError if expected columns are absent from df."""
    missing = []
    if x_col not in df.columns:
        missing.append(x_col)
    if y_col not in df.columns:
        missing.append(y_col)
    if missing:
        raise ValueError(
            f"Column(s) {missing} not found in query result.\n"
            f"Available columns: {list(df.columns)}"
        )


def _pretty(col_name: str) -> str:
    """Convert snake_case column name to Title Case for axis labels."""
    return col_name.replace("_", " ").title()


# ── Summary stats helper ──────────────────────────────────────────────────────
def get_summary_stats(df: pd.DataFrame, y_col: str) -> dict:
    """
    Return a small dict of summary statistics for the Y column.
    Used by app.py to display KPI cards below the chart.
    """
    if y_col not in df.columns:
        return {}

    series = pd.to_numeric(df[y_col], errors="coerce").dropna()
    if series.empty:
        return {}

    return {
        "Total"  : f"{series.sum():,.2f}",
        "Average": f"{series.mean():,.2f}",
        "Max"    : f"{series.max():,.2f}",
        "Min"    : f"{series.min():,.2f}",
        "Rows"   : str(len(df)),
    }
