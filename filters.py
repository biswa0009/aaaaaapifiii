"""
filters.py
----------
PowerBI-style sidebar filter panel.

State lives in  st.session_state["bi_filters"].
Two public entry points used by app.py:
  render_filter_panel(full_df)  — draws widgets in the sidebar
  inject_filters(sql)           — rewrites an LLM SQL to respect active filters
  get_where_clause()            — raw WHERE fragment (used by dashboard.py)
  get_filter_summary()          — human-readable one-liner for the LLM prompt
"""

from __future__ import annotations
import re
import streamlit as st
import pandas as pd

# ── Default state ─────────────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "regions"    : [],
    "categories" : [],
    "payments"   : [],
    "date_start" : None,
    "date_end"   : None,
}


def init_filters() -> None:
    if "bi_filters" not in st.session_state:
        st.session_state["bi_filters"] = _DEFAULTS.copy()


# ── Sidebar renderer ──────────────────────────────────────────────────────────
def render_filter_panel(full_df: pd.DataFrame) -> None:
    """Draw filter widgets inside the sidebar. Call from within `with st.sidebar:`."""
    init_filters()
    f = st.session_state["bi_filters"]

    st.markdown('<div style="font-size:14px; font-weight:700; margin-bottom:12px; display:flex; align-items:center; gap:16px">:material/filter_list: Filters</div>', unsafe_allow_html=True)

    # Region
    regions = sorted(full_df["customer_region"].dropna().unique())
    f["regions"] = st.multiselect(
        "Region", regions,
        default = [r for r in f["regions"] if r in regions],
        key     = "filt_region",
    )

    # Product category
    cats = sorted(full_df["product_category"].dropna().unique())
    f["categories"] = st.multiselect(
        "Category", cats,
        default = [c for c in f["categories"] if c in cats],
        key     = "filt_cat",
    )

    # Payment method
    pays = sorted(full_df["payment_method"].dropna().unique())
    f["payments"] = st.multiselect(
        "Payment Method", pays,
        default = [p for p in f["payments"] if p in pays],
        key     = "filt_pay",
    )

    # Date range
    if pd.api.types.is_datetime64_any_dtype(full_df["order_date"]):
        mn = full_df["order_date"].min().date()
        mx = full_df["order_date"].max().date()
    else:
        mn, mx = None, None

    if mn and mx:
        from datetime import date
        d_start = st.date_input(
            "From", value=f["date_start"] or mn,
            min_value=mn, max_value=mx, key="filt_ds",
        )
        d_end = st.date_input(
            "To",   value=f["date_end"] or mx,
            min_value=mn, max_value=mx, key="filt_de",
        )
        f["date_start"] = d_start
        f["date_end"]   = d_end

    # Status badge + reset
    n = _count_active(f)
    if n:
        st.markdown(f'<div style="font-size:12px; color:var(--primary); margin:8px 0">:material/info: {n} filter{"s" if n > 1 else ""} active</div>', unsafe_allow_html=True)
        if st.button("Reset Filters", icon=":material/refresh:", use_container_width=True, key="filt_reset"):
            st.session_state["bi_filters"] = _DEFAULTS.copy()
            st.rerun()
    else:
        st.markdown('<div style="font-size:12px; color:var(--text-dim); margin:8px 0">:material/check_circle: All data shown</div>', unsafe_allow_html=True)


# ── WHERE clause builder ──────────────────────────────────────────────────────
def get_where_clause() -> str:
    """
    Return a SQL WHERE fragment (without the 'WHERE' keyword).
    Returns empty string when no filters are active.
    """
    init_filters()
    f   = st.session_state["bi_filters"]
    cls = []

    if f.get("regions"):
        vals = ", ".join(f"'{_esc(r)}'" for r in f["regions"])
        cls.append(f"customer_region IN ({vals})")

    if f.get("categories"):
        vals = ", ".join(f"'{_esc(c)}'" for c in f["categories"])
        cls.append(f"product_category IN ({vals})")

    if f.get("payments"):
        vals = ", ".join(f"'{_esc(p)}'" for p in f["payments"])
        cls.append(f"payment_method IN ({vals})")

    if f.get("date_start"):
        cls.append(f"order_date >= '{f['date_start']}'")
    if f.get("date_end"):
        cls.append(f"order_date <= '{f['date_end']}'")

    return " AND ".join(cls)


def get_filter_summary() -> str:
    """One-liner for injecting into the LLM prompt context."""
    init_filters()
    f   = st.session_state["bi_filters"]
    parts = []

    if f.get("regions"):
        parts.append("regions: " + ", ".join(f["regions"]))
    if f.get("categories"):
        parts.append("categories: " + ", ".join(f["categories"]))
    if f.get("payments"):
        parts.append("payment methods: " + ", ".join(f["payments"]))
    if f.get("date_start") or f.get("date_end"):
        parts.append(f"date range: {f.get('date_start','*')} to {f.get('date_end','*')}")

    return ("Active filters — " + "; ".join(parts)) if parts else ""


# ── SQL injector ──────────────────────────────────────────────────────────────
def inject_filters(sql: str) -> str:
    """
    Rewrite *sql* to include the active filter WHERE conditions.
    Handles existing WHERE, GROUP BY, ORDER BY, and bare SELECT...FROM patterns.
    Does nothing when no filters are active.
    """
    where = get_where_clause()
    if not where:
        return sql

    # Case 1 — existing WHERE clause: insert conditions right after WHERE
    m = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
    if m:
        pos = m.end()
        return sql[:pos] + f" {where} AND " + sql[pos:].lstrip()

    # Case 2 — no WHERE yet: insert before GROUP BY / ORDER BY / HAVING / LIMIT
    for kw in [r"\bGROUP\s+BY\b", r"\bORDER\s+BY\b", r"\bHAVING\b", r"\bLIMIT\b"]:
        m = re.search(kw, sql, re.IGNORECASE)
        if m:
            pos = m.start()
            return sql[:pos] + f"WHERE {where} " + sql[pos:]

    # Case 3 — nothing to hook into: append at end
    return sql.rstrip().rstrip(";") + f" WHERE {where}"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _count_active(f: dict) -> int:
    return sum([
        bool(f.get("regions")),
        bool(f.get("categories")),
        bool(f.get("payments")),
        bool(f.get("date_start") or f.get("date_end")),
    ])


def _esc(s: str) -> str:
    """Minimal SQL-string escaping (single-quote doubling)."""
    return str(s).replace("'", "''")
