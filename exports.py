"""
exports.py
----------
Provides download buttons for:
  1. Query result as CSV
  2. Plotly chart as a static PNG image  (requires kaleido)
  3. Full chart metadata as JSON

These are rendered by app.py in an "Export" row below each chart.
All functions are side-effect-free — they return Streamlit button widgets.
"""

from __future__ import annotations
import io
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ── CSV download ──────────────────────────────────────────────────────────────
def csv_download_button(df: pd.DataFrame, filename: str = "query_result.csv") -> None:
    """Render a Streamlit download button that streams df as CSV."""
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label     = "⬇️ Download CSV",
        data      = csv_bytes,
        file_name = filename,
        mime      = "text/csv",
        use_container_width = True,
    )


# ── PNG chart download ────────────────────────────────────────────────────────
def png_download_button(fig: go.Figure, filename: str = "chart.png") -> None:
    """
    Render a PNG download button for the Plotly figure.

    Requires 'kaleido' (listed in requirements.txt).
    Falls back gracefully with an info message if kaleido is absent.
    """
    try:
        img_bytes = fig.to_image(format="png", width=1200, height=600, scale=2)
        st.download_button(
            label     = "🖼️ Download PNG",
            data      = img_bytes,
            file_name = filename,
            mime      = "image/png",
            use_container_width = True,
        )
    except Exception:
        st.info("Install `kaleido` to enable PNG export: `pip install kaleido`")


# ── JSON metadata download ────────────────────────────────────────────────────
def json_download_button(chart_meta: dict, filename: str = "chart_config.json") -> None:
    """Render a download button for the raw LLM chart metadata JSON."""
    json_str = json.dumps(chart_meta, indent=2).encode("utf-8")
    st.download_button(
        label     = "📋 Download JSON",
        data      = json_str,
        file_name = filename,
        mime      = "application/json",
        use_container_width = True,
    )


# ── Composite export row ──────────────────────────────────────────────────────
def render_export_row(
    df         : pd.DataFrame,
    fig        : go.Figure,
    chart_meta : dict,
    question   : str,
) -> None:
    """
    Render a labelled row of all three export buttons.
    Call this once after st.plotly_chart().
    """
    # Derive a safe filename base from the question
    safe = "".join(c if c.isalnum() or c in " _-" else "" for c in question)
    safe = safe.strip().replace(" ", "_")[:40] or "chart"

    with st.expander("⬇️ Export"):
        col1, col2, col3 = st.columns(3)
        with col1:
            csv_download_button(df,         filename=f"{safe}.csv")
        with col2:
            png_download_button(fig,        filename=f"{safe}.png")
        with col3:
            json_download_button(chart_meta, filename=f"{safe}_config.json")
