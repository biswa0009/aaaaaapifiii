"""
history.py
----------
Manages a lightweight in-session query history stored in
st.session_state["query_history"].

Each history entry is a dict:
{
    "question"   : str              – original user question
    "chart_meta" : dict             – {sql_query, chart_type, x_axis, y_axis}
    "df"         : pd.DataFrame     – query result
    "insight"    : str              – AI-generated insight (may be empty)
    "timestamp"  : str              – HH:MM:SS
}

The history list is capped at MAX_HISTORY items (oldest removed first).
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import datetime

MAX_HISTORY = 10       # Keep at most this many past queries in sidebar


# ── Initialisation ────────────────────────────────────────────────────────────
def ensure_history() -> None:
    """Call once at app startup to initialise the history list."""
    if "query_history" not in st.session_state:
        st.session_state["query_history"] = []


# ── Add an entry ──────────────────────────────────────────────────────────────
def add_to_history(
    question   : str,
    chart_meta : dict,
    df         : pd.DataFrame,
    insight    : str = "",
) -> None:
    """Prepend a new result to the history, capped at MAX_HISTORY."""
    ensure_history()
    entry = {
        "question"   : question,
        "chart_meta" : chart_meta,
        "df"         : df.copy(),
        "insight"    : insight,
        "timestamp"  : datetime.now().strftime("%H:%M:%S"),
    }
    history: list = st.session_state["query_history"]
    history.insert(0, entry)                   # newest first
    if len(history) > MAX_HISTORY:
        history.pop()                          # drop oldest


# ── Retrieve ──────────────────────────────────────────────────────────────────
def get_history() -> list[dict]:
    """Return the full history list (newest first)."""
    ensure_history()
    return st.session_state["query_history"]


def clear_history() -> None:
    """Wipe the history."""
    st.session_state["query_history"] = []


# ── Sidebar renderer ──────────────────────────────────────────────────────────
def render_history_sidebar() -> str | None:
    """
    Render the history section inside the Streamlit sidebar.

    Returns the question string if the user clicked a history button
    (so app.py can re-run that question), otherwise None.
    """
    history = get_history()
    if not history:
        st.caption("No queries yet — ask something above!")
        return None

    rerun_question = None

    for i, entry in enumerate(history):
        q         = entry["question"]
        ts        = entry["timestamp"]
        ct        = entry["chart_meta"].get("chart_type", "?")
        icon      = {"bar": "📊", "line": "📈", "pie": "🥧"}.get(ct, "📊")
        short_q   = q if len(q) <= 42 else q[:39] + "…"

        col_label, col_btn = st.columns([5, 1])
        with col_label:
            st.markdown(
                f"<small style='color:#888'>{ts}</small><br>"
                f"{icon} <span style='font-size:0.85rem'>{short_q}</span>",
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("↩", key=f"rerun_{i}", help=f"Re-run: {q}"):
                rerun_question = q

        st.divider()

    if st.button("🗑️ Clear History", use_container_width=True):
        clear_history()
        st.rerun()

    return rerun_question
