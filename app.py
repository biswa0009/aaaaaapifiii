"""
app.py  (v7 — UI Restored & Reorganized)
-----------------------------------------
Clean enterprise BI dashboard. All features accessible within 1-2 clicks.

Architecture:
  - Pure st.tabs() routing (no current_page session state routing)
  - Sidebar: Upload CTA + API key + Quick Analytics + Chart Style + Filters
  - Top navbar: logo + dataset name + search + theme toggle
  - 7 tabs: Dashboard | Data Explorer | About | AI Chat | Analytics | Recommendations | Forecast
  - No duplicate widget keys anywhere
"""

import os
import io as _io
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from database        import init_db, run_query, TABLE_NAME
from llm             import ask_groq
from chart_generator import build_chart, get_summary_stats
from insights        import generate_insight
from history         import ensure_history, add_to_history, render_history_sidebar
from exports         import render_export_row
from filters         import init_filters, render_filter_panel, get_where_clause, \
                            inject_filters, get_filter_summary
from dashboard       import generate_dashboard, get_drilldown_sql, can_drilldown, \
                            _build as _dash_build, _trim as _dash_trim, \
                            generate_adaptive_dashboard
from themes          import PALETTES, get_palette
from _css            import get_css
from anomaly         import detect_anomalies, format_anomaly_html, get_followup_suggestions
from ingestion       import ingest_file, detect_column_types, generate_dataset_summary
from analytics_agent import generate_analytics_report, generate_ai_business_insights
from recommendation_agent import (
    generate_recommendations, enrich_recommendations_with_llm,
    recommendations_to_df,
)
from forecasting     import run_forecast, detect_available_forecaster
from chat_agent      import ask_agent

# ── Page config (MUST be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title            = "biswa BI",
    page_icon             = "■",
    layout                = "wide",
    initial_sidebar_state = "expanded",
)

# ── Session state bootstrap ───────────────────────────────────────────────────
ensure_history()
init_filters()
_DEFAULTS = [
    ("app_theme",           "dark"),
    ("last_result",          None),
    ("auto_execute",         False),
    ("prefill_question",     ""),
    ("chart_type_override",  None),
    ("drill_result",         None),
    ("_last_cust",           None),
    ("chat_messages",        []),
    ("chat_col_map",         {}),
    ("_ai_insights_text",    ""),
    ("_forecast_result",     None),
    ("_analytics_report",    None),
    ("_analytics_df",        None),
    ("_analytics_colmap",    {}),
    ("_dataset_name",        "Built-in dataset"),
    ("_dataset_rows",        50000),
]
for k, v in _DEFAULTS:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Theme-aware CSS injection ─────────────────────────────────────────────────
theme = st.session_state["app_theme"]
st.markdown(get_css(theme), unsafe_allow_html=True)

# ── DB + data (cached) ────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Initialising database…")
def get_db_connection():
    return init_db()

conn = get_db_connection()

@st.cache_data(show_spinner=False)
def load_full_df() -> pd.DataFrame:
    return pd.read_csv("dataset.csv", parse_dates=["order_date"])

full_df = load_full_df()

# ── Customization helper ──────────────────────────────────────────────────────
def get_customization() -> dict:
    page_dark = st.session_state.get("app_theme", "dark") == "dark"
    return {
        "palette"    : st.session_state.get("cust_palette", "biswa"),
        "dark_mode"  : st.session_state.get("cust_dark",    page_dark),
        "top_n"      : st.session_state.get("cust_topn",    0),
        "show_labels": st.session_state.get("cust_labels",  True),
        "sort_asc"   : st.session_state.get("cust_sort",    False),
    }

# ── Auto column mapper ────────────────────────────────────────────────────────
def _auto_map_cols(df: pd.DataFrame) -> dict:
    cols = list(df.columns)
    ct   = detect_column_types(df)
    def _first(candidates, pool):
        for c in candidates:
            if c in pool: return c
        return None
    return {
        "date":    _first(ct["datetime"] + [c for c in cols if "date" in c.lower()], cols),
        "value":   _first([c for c in ct["numeric"] if any(k in c.lower() for k in ("revenue","sales","amount","total"))] + ct["numeric"], cols),
        "product": _first([c for c in ct["categorical"] if any(k in c.lower() for k in ("product","category","item"))], cols),
        "region":  _first([c for c in ct["categorical"] if any(k in c.lower() for k in ("region","country","location","area"))], cols),
    }

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:

    # Brand
    st.markdown(
        '<div class="sb-brand">'
        '<div class="sb-brand-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg></div>'
        '<div><div class="sb-brand-name">biswa BI</div>'
        '<div class="sb-brand-sub">Modern Analytics</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Upload Dataset — PRIMARY CTA ──────────────────────────────────────────
    st.markdown('<div class="upload-cta-wrap">', unsafe_allow_html=True)
    uploaded_sb = st.file_uploader(
        "Upload Dataset (CSV / Excel)",
        type=["csv", "xlsx", "xls"],
        key="sb_upload",
        label_visibility="collapsed",
        help="Upload any CSV or Excel file to analyse it",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # Process upload and share via session state
    if uploaded_sb is not None:
        try:
            raw = uploaded_sb.read()
            fn  = uploaded_sb.name
            fo  = _io.StringIO(raw.decode("utf-8", errors="replace")) if fn.lower().endswith(".csv") else _io.BytesIO(raw)
            _df, _ir = ingest_file(fo)
            st.session_state["_analytics_df"]     = _df
            st.session_state["_analytics_colmap"] = _auto_map_cols(_df)
            st.session_state["_dataset_name"]     = fn
            st.session_state["_dataset_rows"]     = len(_df)
            st.session_state["_analytics_report"] = None   # trigger re-analysis
            if _ir and _ir.get("cleaning_report"):
                cr = _ir["cleaning_report"]
                st.success(f"✅ {fn} loaded · {len(_df):,} rows · {cr['duplicates_dropped']} dupes dropped")
        except Exception as _exc:
            st.error(f"Upload failed: {_exc}")

    # Dataset info pill
    dname = st.session_state.get("_dataset_name", "Built-in dataset")
    drows = st.session_state.get("_dataset_rows", 50000)
    st.markdown(
        f'<div class="dataset-badge">📁 <strong>{dname}</strong> · {drows:,} rows</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── API key ───────────────────────────────────────────────────────────────
    st.markdown('''<div class="sb-section-label">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>
        API Configuration</div>''', unsafe_allow_html=True)
    api_key = st.text_input(
        "Groq API Key", type="password",
        placeholder="gsk_…  (or set GROQ_API_KEY env var)",
        label_visibility="collapsed",
        key="sb_api_key",
    )
    if api_key.strip():
        os.environ["GROQ_API_KEY"] = api_key.strip()
    if not os.environ.get("GROQ_API_KEY", "").strip():
        st.markdown(
            '<div style="font-size:11px;color:var(--warning);padding:4px 2px">'
            '⚠ Groq API key required — get one free at console.groq.com'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Quick Analytics shortcuts ─────────────────────────────────────────────
    st.markdown('''<div class="sb-section-label">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
        Quick Analytics</div>''', unsafe_allow_html=True)

    QUICK_ANALYTICS = [
        ("Revenue by product category",      ":material/inventory_2:"),
        ("Revenue by customer region",       ":material/language:"),
        ("Monthly revenue trend 2023",       ":material/monitoring:"),
        ("Revenue share by payment method",  ":material/wallet:"),
        ("Average rating per category",      ":material/reviews:"),
        ("Top 5 categories by quantity sold", ":material/leaderboard:"),
        ("Average discount percentage by region", ":material/local_offer:"),
        ("Total revenue by month in 2022",   ":material/event_note:"),
        ("Highest avg order value by payment method", ":material/monetization_on:"),
        ("Revenue breakdown by region and category",  ":material/hub:"),
    ]
    for q, icon in QUICK_ANALYTICS:
        if st.button(f"{q}", icon=icon, use_container_width=True, key=f"qq_{q[:30]}"):
            st.session_state["prefill_question"] = q
            st.session_state["auto_execute"]     = True
            st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Chart Style ───────────────────────────────────────────────────────────
    st.markdown('''<div class="sb-section-label">Chart Style</div>''', unsafe_allow_html=True)
    st.selectbox(
        "Color Theme", list(PALETTES.keys()), index=0,
        key="cust_palette", label_visibility="collapsed",
    )
    cs1, cs2 = st.columns(2)
    with cs1:
        dark_default = st.session_state.get("app_theme", "dark") == "dark"
        st.toggle("Dark Charts", value=dark_default, key="cust_dark")
    with cs2:
        st.toggle("Data Labels", value=True, key="cust_labels")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Data Controls ─────────────────────────────────────────────────────────
    st.markdown('''<div class="sb-section-label">Data Controls</div>''', unsafe_allow_html=True)
    st.slider("Top N  (0 = show all)", 0, 30, 0, key="cust_topn")
    st.toggle("Sort Ascending", value=False, key="cust_sort")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Filters ───────────────────────────────────────────────────────────────
    st.markdown('''<div class="sb-section-label">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
        Filters</div>''', unsafe_allow_html=True)
    render_filter_panel(full_df)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Recent queries ────────────────────────────────────────────────────────
    st.markdown('''<div class="sb-section-label">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></svg>
        Recent Queries</div>''', unsafe_allow_html=True)
    rerun_q = render_history_sidebar()
    if rerun_q:
        st.session_state["prefill_question"] = rerun_q
        st.session_state["auto_execute"]     = True
        st.rerun()

    st.markdown(
        f'<div style="padding:12px 0 4px;font-size:11px;color:var(--text-dim)">'
        f'📁 {TABLE_NAME} · 50 000 rows · 13 cols · 2022–2023</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOP NAVBAR
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="sticky-nav">', unsafe_allow_html=True)
nav_c1, nav_c2, nav_c3 = st.columns([3, 5, 2])
with nav_c1:
    st.markdown(
        '<div class="nav-left">'
        '<div class="nav-logo">biswa BI</div>'
        '<div class="nav-title">Enterprise Dashboard</div>'
        '</div>',
        unsafe_allow_html=True,
    )
with nav_c2:
    nav_search = st.text_input(
        "nav_search",
        placeholder="🔍 Search or ask a business question…",
        label_visibility="collapsed",
        key="navbar_search",
    )
    if nav_search.strip():
        st.session_state["prefill_question"] = nav_search.strip()
        st.session_state["auto_execute"]     = True
with nav_c3:
    t_col, ai_col_btn = st.columns(2)
    with t_col:
        is_dark = (theme == "dark")
        if st.button("☀️" if is_dark else "🌙", key="theme_toggle", help="Switch theme", use_container_width=True):
            st.session_state["app_theme"] = "light" if is_dark else "dark"
            st.rerun()
    with ai_col_btn:
        if st.button("🤖", key="ai_tab_hint", help="Go to AI Chat tab", use_container_width=True):
            st.session_state["_jump_to_chat"] = True
            st.rerun()
st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TABS  — unified routing via st.tabs() only
# ─────────────────────────────────────────────────────────────────────────────
(tab_dash, tab_explorer, tab_about,
 tab_chat, tab_analytics, tab_recs, tab_forecast) = st.tabs([
    "🏠 Dashboard",
    "🔍 Data Explorer",
    "ℹ️ About",
    "🤖 AI Chat",
    "📊 Analytics",
    "💡 Recommendations",
    "📈 Forecast",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    prefill      = st.session_state.pop("prefill_question", "")
    auto_execute = st.session_state.pop("auto_execute",     False)

    # ── Query bar ─────────────────────────────────────────────────────────────
    st.markdown('<div class="glass-card query-bar-wrapper">', unsafe_allow_html=True)
    st.markdown('<div class="query-bar-label">Ask a Business Question</div>', unsafe_allow_html=True)
    qcol, bcol, xcol = st.columns([6.5, 2.5, 1.5])
    with qcol:
        question = st.text_input(
            "q", value=prefill,
            placeholder="Ask a business question…  e.g. revenue by category, monthly trends, top products",
            label_visibility="collapsed",
            key="q_input",
        )
    with bcol:
        run_btn = st.button("⚡ Analyze Data", type="primary", use_container_width=True)
    with xcol:
        if st.button("Clear", use_container_width=True, help="Clear dashboard"):
            st.session_state["last_result"]  = None
            st.session_state["drill_result"] = None
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    def _need_key() -> bool:
        if not os.environ.get("GROQ_API_KEY", "").strip():
            st.error("⚠  Set your Groq API key in the sidebar to continue.")
            return True
        return False

    should_run = (run_btn and question.strip()) or (auto_execute and question.strip())

    # ── 4-stage pipeline ──────────────────────────────────────────────────────
    if should_run:
        if _need_key():
            st.stop()

        cust    = get_customization()
        where   = get_where_clause()
        flt_ctx = get_filter_summary()

        pc = st.empty()
        STEPS = [
            "① Sending question to Groq LLM (llama-3.3-70b-versatile)…",
            "② Running SQL query on 50 000-row dataset…",
            "③ Building multi-chart dashboard panels…",
            "④ Generating AI business insight…",
        ]

        def _show_step(i: int) -> None:
            pc.markdown(
                f'<div class="glass-card" style="margin-bottom:16px">'
                f'<div class="chart-card-header">'
                f'<span class="chart-card-title">Processing your question…</span>'
                f'<span class="chart-card-badge">Step {i+1}/4</span>'
                f'</div>'
                f'<div style="margin-top:10px;color:var(--text-muted);font-size:13px">'
                f'{STEPS[i]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        prog = st.progress(0)
        _show_step(0)

        try:
            chart_meta = ask_groq(question, filter_context=flt_ctx)
        except ValueError as e:
            prog.empty(); pc.empty()
            st.error(f"**LLM Error:** {e}"); st.stop()

        prog.progress(30); _show_step(1)

        sql     = inject_filters(chart_meta["sql_query"])
        df, err = run_query(conn, sql)
        if err:
            prog.empty(); pc.empty()
            st.error(f"**Database Error:** {err}")
            with st.expander("Generated SQL (debug)"):
                st.code(sql, language="sql")
            st.stop()

        prog.progress(60); _show_step(2)

        try:
            panels = generate_dashboard(conn, df, chart_meta, where, cust)
        except Exception as e:
            prog.empty(); pc.empty()
            st.error(f"**Chart Error:** {e}"); st.stop()

        prog.progress(82); _show_step(3)

        insight  = generate_insight(question, df, chart_meta.get("y_axis", ""))
        x_col    = chart_meta.get("x_axis", "")
        y_col    = chart_meta.get("y_axis", "")
        anomalies = detect_anomalies(df, y_col, x_col)

        prog.progress(100); prog.empty(); pc.empty()

        st.session_state["last_result"] = {
            "question"  : question,
            "chart_meta": chart_meta,
            "df"        : df,
            "panels"    : panels,
            "insight"   : insight,
            "sql"       : sql,
            "anomalies" : anomalies,
        }
        st.session_state["drill_result"]        = None
        st.session_state["chart_type_override"] = None
        add_to_history(question, chart_meta, df, insight)
        st.rerun()

    elif run_btn and not question.strip():
        st.warning("Type a question first.")

    # ── Render results ────────────────────────────────────────────────────────
    result = st.session_state.get("last_result")

    if result:
        cust       = get_customization()
        chart_meta = result["chart_meta"]
        df         = result["df"]
        panels     = result["panels"]
        x_col      = chart_meta["x_axis"]
        y_col      = chart_meta["y_axis"]
        anomalies  = result.get("anomalies", [])

        # Status
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">'
            f'<span style="font-size:12px;color:var(--success);background:rgba(16,185,129,.1);'
            f'border:1px solid rgba(16,185,129,.2);border-radius:20px;padding:3px 10px;font-weight:500">'
            f'Dashboard Ready</span>'
            f'<span style="font-size:13px;color:var(--text-muted)">'
            f'<em>{result["question"]}</em></span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Chart-type switcher
        CTYPE_MAP = {
            "Auto": None, "Bar": "bar", "Line": "line", "Pie": "pie",
            "Area": "area", "Scatter": "scatter", "Histogram": "histogram",
        }
        sel_label = st.radio(
            "ct", list(CTYPE_MAP.keys()), index=0, horizontal=True,
            label_visibility="collapsed", key="chart_radio",
        )
        override = CTYPE_MAP.get(sel_label)

        # KPI metric row
        stats = get_summary_stats(df, y_col)
        if stats:
            kpi_cols = st.columns(len(stats))
            for col_w, (lbl, val) in zip(kpi_cols, stats.items()):
                col_w.metric(lbl, val)

        st.markdown('<div style="margin-top:8px"></div>', unsafe_allow_html=True)

        # Rebuild panels on override or customization change
        if override is not None or cust != st.session_state.get("_last_cust"):
            st.session_state["_last_cust"] = cust
            try:
                panels = generate_dashboard(conn, df, chart_meta, get_where_clause(), cust)
                if override and panels:
                    pal = get_palette(cust["palette"])
                    d0  = _dash_trim(df.copy(), y_col, cust["top_n"], cust["sort_asc"])
                    panels[0]["fig"] = _dash_build(
                        d0, x_col, y_col, override, pal,
                        cust["dark_mode"], "", cust["show_labels"],
                    )
            except Exception:
                pass

        # 2-column chart grid
        CT_BADGE = {
            "bar": "Bar", "line": "Line", "pie": "Pie", "area": "Area",
            "scatter": "Scatter", "histogram": "Histogram",
            "trend": "Trend", "companion": "Share", "primary": "Chart",
        }
        for pair in [panels[i:i+2] for i in range(0, len(panels), 2)]:
            grid_cols = st.columns(len(pair))
            for gc, panel in zip(grid_cols, pair):
                with gc:
                    badge = CT_BADGE.get(panel["panel_id"], panel["panel_id"].title())
                    st.markdown(
                        f'<div class="glass-card">'
                        f'<div class="chart-card-header">'
                        f'<span class="chart-card-title">{panel["title"]}</span>'
                        f'<span class="chart-card-badge">{badge}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(
                        panel["fig"],
                        use_container_width=True,
                        key=f"chart_{panel['panel_id']}",
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

        # Data table
        with st.expander(f"📋 Data Table ({len(df):,} rows)"):
            st.dataframe(
                df.sort_values(by=y_col, ascending=False).reset_index(drop=True),
                use_container_width=True, hide_index=True,
            )

        # AI Insight
        if result["insight"]:
            st.markdown(
                f'<div class="glass-card insight-card">'
                f'<div class="insight-title">AI Insight</div>'
                f'<div class="insight-body">{result["insight"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Anomaly Detection
        if anomalies:
            items_html = "".join(
                f'<div class="anomaly-item">{format_anomaly_html(a, y_col)}</div>'
                for a in anomalies
            )
            st.markdown(
                f'<div class="glass-card anomaly-card">'
                f'<div class="anomaly-title">Anomaly Detection — {len(anomalies)} unusual value{"s" if len(anomalies) > 1 else ""} found</div>'
                f'{items_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Follow-up chips
        suggestions = get_followup_suggestions(x_col, y_col)
        if suggestions:
            st.markdown(
                '<div class="glass-card followup-card">'
                '<div class="followup-title">Explore Further</div>',
                unsafe_allow_html=True,
            )
            sug_cols = st.columns(len(suggestions))
            for sc, (icon, q) in zip(sug_cols, suggestions):
                with sc:
                    if st.button(f"{icon}  {q}", use_container_width=True, key=f"sug_{q[:40]}"):
                        st.session_state["prefill_question"] = q
                        st.session_state["auto_execute"]     = True
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        # Drill-Down
        st.markdown('<div class="section-label">🔍 Drill-Down Analysis</div>', unsafe_allow_html=True)
        if not can_drilldown(x_col):
            st.markdown(
                '<div style="font-size:13px;color:var(--text-dim);padding:8px 0">'
                'No deeper dimension available. Drill-down works on categorical dimensions: '
                '<strong>region</strong>, <strong>category</strong>, <strong>payment method</strong>.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            drill_options = df[x_col].dropna().unique().tolist()
            da, db_ = st.columns([3, 1])
            with da:
                sv = st.selectbox(
                    f"Drill into {x_col.replace('_',' ')}",
                    ["— Select a value —"] + [str(v) for v in drill_options],
                    key="drill_select", label_visibility="collapsed",
                )
            with db_:
                drill_btn = st.button("Drill In", use_container_width=True, key="drill_go")

            if drill_btn and sv != "— Select a value —":
                dinfo = get_drilldown_sql(x_col, sv, y_col, get_where_clause())
                if dinfo:
                    dsql, bc = dinfo
                    ddf, derr = run_query(conn, dsql)
                    if derr:
                        st.error(f"Drill error: {derr}")
                    else:
                        pal  = get_palette(cust["palette"])
                        ddf2 = _dash_trim(ddf.copy(), y_col, cust["top_n"], cust["sort_asc"])
                        dfig = _dash_build(ddf2, bc, y_col, "bar", pal, cust["dark_mode"], "", cust["show_labels"])
                        st.session_state["drill_result"] = {
                            "fig": dfig, "df": ddf, "label": sv, "x": bc, "y": y_col, "sql": dsql,
                        }
                else:
                    st.info("No drill-down path defined for this dimension.")

        dr = st.session_state.get("drill_result")
        if dr:
            st.markdown(
                f'<div class="glass-card drill-card">'
                f'Drilled into <strong>{dr["label"]}</strong> → '
                f'breakdown by <strong>{dr["x"].replace("_"," ").title()}</strong>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.plotly_chart(dr["fig"], use_container_width=True, key="drill_chart")
            st.markdown("</div>", unsafe_allow_html=True)

            dd1, dd2 = st.columns(2)
            with dd1:
                with st.expander("Drill-Down Data"):
                    st.dataframe(dr["df"], use_container_width=True, hide_index=True)
            with dd2:
                with st.expander("Drill-Down SQL"):
                    st.markdown(
                        f'<div class="glass-card sql-card">'
                        f'<div class="sql-card-header">SQL Query</div>'
                        f'<div class="sql-card-body">{dr["sql"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # Export & Details
        st.markdown('<div class="section-label">📤 Export &amp; Details</div>', unsafe_allow_html=True)
        if panels:
            render_export_row(df, panels[0]["fig"], chart_meta, result["question"])

        ex1, ex2 = st.columns(2)
        with ex1:
            with st.expander("Generated SQL Query"):
                st.markdown(
                    f'<div class="glass-card sql-card">'
                    f'<div class="sql-card-header">SQLite · Auto-generated</div>'
                    f'<div class="sql-card-body">{result["sql"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        with ex2:
            with st.expander("LLM Decision"):
                m = chart_meta
                st.table(pd.DataFrame([{
                    "Title"     : m.get("title", ""),
                    "Chart Type": m.get("chart_type", ""),
                    "X Axis"    : m.get("x_axis", ""),
                    "Y Axis"    : m.get("y_axis", ""),
                }]))

    elif not should_run:
        # Empty state
        st.markdown(
            """
            <div class="glass-card empty-state">
              <div class="empty-icon"><svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg></div>
              <div class="empty-title">Your Dashboard Awaits</div>
              <div class="empty-sub">
                Type a business question above — or click a <strong>Quick Analytics</strong>
                shortcut in the sidebar. The AI generates a full multi-chart dashboard,
                AI insight, and anomaly detection in seconds.
              </div>
              <div style="margin-top:28px">
                <span class="chip">Revenue by category</span>
                <span class="chip">Monthly trends</span>
                <span class="chip">Regional analysis</span>
                <span class="chip">Payment insights</span>
                <span class="chip">Spot anomalies</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 · DATA EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
with tab_explorer:

    st.markdown(
        '<div style="margin-bottom:20px">'
        '<div class="page-title" style="font-size:22px">🔍 Data Explorer</div>'
        '<div class="page-subtitle">Filter, search, and export all 50 000 rows</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.expander("⚙️ Filter Controls", expanded=True):
        fe1, fe2, fe3, fe4 = st.columns(4)
        with fe1:
            sel_cat = st.selectbox(
                "Category", ["All"] + sorted(full_df["product_category"].unique()), key="ex_cat",
            )
        with fe2:
            sel_reg = st.selectbox(
                "Region", ["All"] + sorted(full_df["customer_region"].unique()), key="ex_reg",
            )
        with fe3:
            sel_pay = st.selectbox(
                "Payment Method", ["All"] + sorted(full_df["payment_method"].unique()), key="ex_pay",
            )
        with fe4:
            lo = float(full_df["total_revenue"].min())
            hi = float(full_df["total_revenue"].max())
            rev_range = st.slider("Revenue Range", lo, hi, (lo, hi), step=50.0, key="ex_rev")

    flt = full_df.copy()
    if sel_cat != "All": flt = flt[flt["product_category"] == sel_cat]
    if sel_reg != "All": flt = flt[flt["customer_region"]  == sel_reg]
    if sel_pay != "All": flt = flt[flt["payment_method"]   == sel_pay]
    flt = flt[(flt["total_revenue"] >= rev_range[0]) & (flt["total_revenue"] <= rev_range[1])]

    srch = st.text_input(
        "Search all columns",
        placeholder="e.g. Books, Asia, UPI…",
        key="ex_srch",
    )
    if srch.strip():
        mask = flt.astype(str).apply(
            lambda c: c.str.contains(srch.strip(), case=False, na=False)
        ).any(axis=1)
        flt = flt[mask]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rows Shown",    f"{len(flt):,}")
    m2.metric("Total Revenue", f"${flt['total_revenue'].sum():,.0f}")
    m3.metric("Avg Rating",    f"{flt['rating'].mean():.2f}" if len(flt) else "—")
    m4.metric("Avg Discount",  f"{flt['discount_percent'].mean():.1f}%" if len(flt) else "—")

    st.divider()

    dcols = ["order_id", "order_date", "product_category", "customer_region", "quantity_sold", "total_revenue", "rating"]
    sel_cols = st.multiselect("Visible Columns", list(full_df.columns), default=dcols, key="ex_cols")
    st.dataframe(
        flt[sel_cols or list(full_df.columns)].reset_index(drop=True),
        use_container_width=True, hide_index=True, height=460,
    )
    st.download_button(
        "⬇️ Download Filtered CSV",
        data      = flt[sel_cols or list(full_df.columns)].to_csv(index=False).encode(),
        file_name = "filtered_data.csv",
        mime      = "text/csv",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 · ABOUT
# ══════════════════════════════════════════════════════════════════════════════
with tab_about:

    st.markdown(
        '<div style="margin-bottom:24px">'
        '<div class="page-title" style="font-size:22px">ℹ️ About</div>'
        '<div class="page-subtitle">Architecture, design system, and dataset reference</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.markdown("""
### Pipeline
```
Natural language question + filter context
              │
              ▼
         Groq LLM
    llama-3.3-70b-versatile
              │
    JSON { sql, chart_type, x, y, title }
              │
       inject_filters(sql)
              │
       SQLite execution
              │
       pandas DataFrame
              │
    ┌─────────┴──────────┐
    ▼                    ▼
generate_dashboard()  detect_anomalies()
  Bar · Pie · Trend        z-score
    │                    │
    └─────────┬──────────┘
              │
    generate_insight()
    (Groq, non-blocking)
              │
              ▼
    KPIs · Chart Grid · AI Insight
    Anomalies · Follow-up Chips
    Drill-Down · Exports
```

### Files
| File | Role |
|---|---|
| `app.py` | UI, layout, orchestration |
| `_css.py` | Dark + light CSS design system |
| `anomaly.py` | Z-score anomaly detection |
| `llm.py` | Groq API + prompt + JSON parse |
| `database.py` | SQLite + safe query executor |
| `dashboard.py` | Multi-chart + drill-down + adaptive |
| `chat_agent.py` | Conversational AI agent |
| `analytics_agent.py` | Full analytics report engine |
| `forecasting.py` | Linear / ARIMA / Prophet fallback chain |
| `recommendation_agent.py` | Business recommendation engine |
| `ingestion.py` | CSV/Excel ingest + auto-clean |
| `chart_generator.py` | Single chart facade |
| `filters.py` | Filter panel + SQL injection |
| `themes.py` | Colour palettes + BI default |
| `insights.py` | AI insight writer |
| `history.py` | Session query history |
| `exports.py` | CSV / PNG / JSON downloads |
        """)

    with col_r:
        st.markdown("""
### Design system
| Token | Dark | Light |
|---|---|---|
| Background | `#050505` | `#F4F4F8` |
| Card | rgba(15,15,15,0.6) | rgba(255,255,255,0.95) |
| Primary | `#8B5CF6` | `#7C3AED` |
| Success | `#10B981` | `#059669` |
| Warning | `#F59E0B` | `#D97706` |
| Font | Plus Jakarta Sans | Plus Jakarta Sans |

### BI Colour Palette
`#6366F1` · `#22C55E` · `#F59E0B`
`#EF4444` · `#06B6D4` · `#A855F7`

### Chart types
Bar · Line · Pie/Donut · Area · Scatter · Histogram
Treemap · Heatmap · Correlation · Geo Map

### Anomaly detection
Z-score threshold: ±2.0σ · max 3 alerts

### Dataset
50 000 orders · 13 columns · 2022–2023
Categories: Books · Fashion · Sports
Beauty · Electronics · Home & Kitchen
Regions: N. America · Asia · Europe · Middle East
        """)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 · AI CHAT
# ══════════════════════════════════════════════════════════════════════════════
with tab_chat:

    st.markdown(
        '<div style="margin-bottom:20px">'
        '<div class="page-title" style="font-size:22px">🤖 AI Chat</div>'
        '<div class="page-subtitle">Ask questions in plain English · get data-driven answers + inline charts</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Active dataset for chat
    chat_ana_df  = st.session_state.get("_analytics_df")
    if chat_ana_df is None: chat_ana_df = full_df
    chat_col_map = st.session_state.get("_analytics_colmap", {})

    if not chat_col_map:
        chat_col_map = _auto_map_cols(chat_ana_df)
        st.session_state["chat_col_map"] = chat_col_map

    # Dataset info banner
    _cn = st.session_state.get("_dataset_name", "Built-in dataset")
    st.markdown(
        f'<div class="dataset-badge">'
        f'📁 Dataset: <strong>{_cn}</strong> · '
        f'{len(chat_ana_df):,} rows × {len(chat_ana_df.columns)} cols · '
        f'Metric: <strong>{chat_col_map.get("value", "auto-detect")}</strong>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Starter chips (only shown when empty)
    _CHAT_STARTERS = [
        ("📉", "Why did sales decrease?"),
        ("🏆", "Which product performed best?"),
        ("🌍", "Compare regions"),
        ("📅", "Show monthly revenue"),
        ("🔮", "Forecast next month"),
    ]

    if not st.session_state["chat_messages"]:
        st.markdown(
            '<div style="text-align:center;padding:40px 0 8px">'
            '<div style="font-size:48px;margin-bottom:16px">💬</div>'
            '<div style="font-size:18px;color:var(--text);font-weight:700;margin-bottom:8px">'
            'Start a conversation about your data</div>'
            '<div style="font-size:14px;color:var(--text-muted);margin-bottom:28px">'
            'Ask anything about trends, products, regions, or forecasts</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        chip_cols = st.columns(len(_CHAT_STARTERS))
        for cc, (icon, question) in zip(chip_cols, _CHAT_STARTERS):
            with cc:
                if st.button(
                    f"{icon} {question}",
                    use_container_width=True,
                    key=f"chat_chip_{question[:18]}",
                ):
                    st.session_state["chat_messages"].append(
                        {"role": "user", "content": question, "fig": None, "chart_title": "", "intent": ""}
                    )
                    with st.spinner("Analyzing data…"):
                        _dm  = st.session_state.get("app_theme", "dark") == "dark"
                        _pal = get_palette(st.session_state.get("cust_palette", "biswa"))
                        _r   = ask_agent(
                            question=question, df=chat_ana_df,
                            col_map=chat_col_map,
                            chat_history=[
                                {"role": m["role"], "content": m["content"]}
                                for m in st.session_state["chat_messages"][:-1]
                            ],
                            palette=_pal, dark=_dm,
                        )
                    st.session_state["chat_messages"].append({
                        "role": "assistant", "content": _r.answer,
                        "fig": _r.fig, "chart_title": _r.chart_title, "intent": _r.intent,
                    })
                    st.rerun()

    # Theme colours for bubbles
    _IS_DARK    = st.session_state.get("app_theme", "dark") == "dark"
    _USER_BG    = "rgba(99,102,241,0.15)" if _IS_DARK else "rgba(99,102,241,0.08)"
    _USER_BDR   = "rgba(99,102,241,0.35)" if _IS_DARK else "rgba(99,102,241,0.3)"
    _AI_BG      = "rgba(31,41,55,0.8)"    if _IS_DARK else "rgba(248,250,252,0.95)"
    _AI_BDR     = "rgba(55,65,81,1)"      if _IS_DARK else "#E5E7EB"
    _TXT        = "#E5E7EB"               if _IS_DARK else "#1F2937"
    _TXT_M      = "#9CA3AF"               if _IS_DARK else "#6B7280"

    # Render conversation
    for _i, _msg in enumerate(st.session_state["chat_messages"]):
        if _msg["role"] == "user":
            st.markdown(
                f'<div style="display:flex;justify-content:flex-end;margin:12px 0 4px">'
                f'<div style="max-width:68%;background:{_USER_BG};'
                f'border:1px solid {_USER_BDR};border-radius:18px 18px 4px 18px;padding:12px 18px">'
                f'<div style="font-size:13px;color:{_TXT};font-weight:500">{_msg["content"]}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        else:
            _badge_html = (
                f'<span style="font-size:10px;background:rgba(99,102,241,0.2);'
                f'color:#818CF8;border-radius:10px;padding:2px 8px;margin-left:8px;'
                f'font-weight:600;text-transform:uppercase;letter-spacing:0.5px">'
                f'{_msg.get("intent","")}</span>'
            ) if _msg.get("intent") else ""

            st.markdown(
                f'<div style="display:flex;justify-content:flex-start;margin:12px 0 4px">'
                f'<div style="max-width:85%;width:100%;background:{_AI_BG};'
                f'border:1px solid {_AI_BDR};border-radius:18px 18px 18px 4px;padding:16px 20px">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
                f'<span style="font-size:18px">🤖</span>'
                f'<span style="font-size:12px;font-weight:700;color:#8B5CF6">AI Analyst</span>'
                f'{_badge_html}</div>'
                f'<div style="font-size:13px;color:{_TXT};line-height:1.7">{_msg["content"]}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            if _msg.get("fig") is not None:
                st.markdown(
                    f'<div style="margin:4px 0 8px 44px;background:{_AI_BG};'
                    f'border:1px solid {_AI_BDR};border-radius:12px;padding:12px 16px">'
                    f'<div style="font-size:12px;color:{_TXT_M};font-weight:600;margin-bottom:8px">'
                    f'📊 {_msg.get("chart_title","Chart")}</div>',
                    unsafe_allow_html=True,
                )
                st.plotly_chart(_msg["fig"], use_container_width=True, key=f"chat_chart_{_i}")
                st.markdown("</div>", unsafe_allow_html=True)

    # Input bar
    st.markdown('<div style="margin-top:20px"></div>', unsafe_allow_html=True)
    _ci, _cs, _cc = st.columns([7, 1.5, 1.5])
    with _ci:
        _chat_input = st.text_input(
            "chat_q", placeholder="Ask anything about your data… e.g. 'Why did sales drop in Q3?'",
            label_visibility="collapsed", key="chat_input_box",
        )
    with _cs:
        _send_btn = st.button("⚡ Send", type="primary", use_container_width=True, key="chat_send")
    with _cc:
        if st.button("🗑 Clear", use_container_width=True, key="chat_clear"):
            st.session_state["chat_messages"] = []
            st.rerun()

    if _send_btn and _chat_input.strip():
        _uq = _chat_input.strip()
        st.session_state["chat_messages"].append(
            {"role": "user", "content": _uq, "fig": None, "chart_title": "", "intent": ""}
        )
        with st.spinner("Thinking…"):
            _dm2  = st.session_state.get("app_theme", "dark") == "dark"
            _pal2 = get_palette(st.session_state.get("cust_palette", "biswa"))
            _r2   = ask_agent(
                question=_uq, df=chat_ana_df, col_map=chat_col_map,
                chat_history=[
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state["chat_messages"][:-1]
                ],
                palette=_pal2, dark=_dm2,
            )
        st.session_state["chat_messages"].append({
            "role": "assistant", "content": _r2.answer,
            "fig": _r2.fig, "chart_title": _r2.chart_title, "intent": _r2.intent,
        })
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 · ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
with tab_analytics:

    st.markdown(
        '<div style="margin-bottom:20px">'
        '<div class="page-title" style="font-size:22px">📊 Analytics Agent</div>'
        '<div class="page-subtitle">Auto-adaptive multi-chart analysis · upload any CSV or Excel · falls back to built-in dataset</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Upload inside tab (duplicates sidebar for discoverability)
    ana_up_col, ana_info_col = st.columns([3, 1])
    with ana_up_col:
        ana_uploaded = st.file_uploader(
            "Upload dataset (CSV or Excel .xlsx)",
            type=["csv", "xlsx", "xls"],
            key="analytics_upload",
            help="Leave empty to use the built-in 50 000-row dataset",
        )
    with ana_info_col:
        st.markdown(
            '<div style="font-size:12px;color:var(--text-muted);padding-top:28px">'
            '💡 Or use the sidebar uploader to share the dataset across all tabs'
            '</div>',
            unsafe_allow_html=True,
        )

    if ana_uploaded is not None:
        try:
            raw_bytes = ana_uploaded.read()
            file_name = ana_uploaded.name
            file_obj  = (
                _io.StringIO(raw_bytes.decode("utf-8", errors="replace"))
                if file_name.lower().endswith(".csv")
                else _io.BytesIO(raw_bytes)
            )
            ana_df, ingest_report = ingest_file(file_obj)
            ingest_source = f"Uploaded: **{file_name}**"
            st.session_state["_analytics_df"]     = ana_df
            st.session_state["_analytics_colmap"] = _auto_map_cols(ana_df)
            st.session_state["_dataset_name"]     = file_name
            st.session_state["_dataset_rows"]     = len(ana_df)
        except Exception as exc:
            st.error(f"Failed to read uploaded file: {exc}")
            ana_df, ingest_report = full_df.copy(), None
            ingest_source = "Built-in dataset (upload failed)"
    else:
        # Use whatever was uploaded via sidebar or fall back to built-in
        ana_df = st.session_state.get("_analytics_df")
        if ana_df is None: ana_df = full_df.copy()
        ingest_report = None
        ingest_source = f"**{st.session_state.get('_dataset_name', 'Built-in dataset')}**"

    st.markdown(
        f'<div class="dataset-badge">📁 {ingest_source} · {len(ana_df):,} rows · {len(ana_df.columns)} columns</div>',
        unsafe_allow_html=True,
    )

    # Dataset summary
    summary   = generate_dataset_summary(ana_df)
    col_types = summary["column_types"]

    st.markdown('<div class="section-label">Dataset Summary</div>', unsafe_allow_html=True)
    sm1, sm2, sm3, sm4, sm5 = st.columns(5)
    sm1.metric("Rows",           f"{summary['n_rows']:,}")
    sm2.metric("Columns",        str(summary['n_cols']))
    sm3.metric("Missing Values", f"{summary['missing_values']:,} ({summary['missing_pct']}%)")
    sm4.metric("Duplicates",     str(summary['duplicates']))
    sm5.metric("Numeric Cols",   str(len(col_types['numeric'])))

    # Column type pills
    pill_html = ""
    for col in col_types["numeric"]:
        pill_html += (
            f'<span style="background:rgba(99,102,241,0.15);color:#818CF8;'
            f'border:1px solid rgba(99,102,241,0.3);border-radius:20px;'
            f'padding:2px 10px;font-size:11px;margin:2px;display:inline-block">🔢 {col}</span>'
        )
    for col in col_types["categorical"]:
        pill_html += (
            f'<span style="background:rgba(16,185,129,0.12);color:#34D399;'
            f'border:1px solid rgba(16,185,129,0.25);border-radius:20px;'
            f'padding:2px 10px;font-size:11px;margin:2px;display:inline-block">🏷 {col}</span>'
        )
    for col in col_types["datetime"]:
        pill_html += (
            f'<span style="background:rgba(245,158,11,0.12);color:#FBBF24;'
            f'border:1px solid rgba(245,158,11,0.25);border-radius:20px;'
            f'padding:2px 10px;font-size:11px;margin:2px;display:inline-block">📅 {col}</span>'
        )
    st.markdown(f'<div style="margin:12px 0 20px">{pill_html}</div>', unsafe_allow_html=True)

    if ingest_report and ingest_report.get("cleaning_report"):
        cr = ingest_report["cleaning_report"]
        st.info(
            f"🧹 **Auto-cleaned:** "
            f"{cr['duplicates_dropped']} duplicates dropped · "
            f"{cr['numeric_filled']} numeric NaNs filled · "
            f"{cr['categorical_filled']} categorical NaNs filled"
        )

    st.markdown("<hr>", unsafe_allow_html=True)

    # Column mapping
    default_map = _auto_map_cols(ana_df)
    with st.expander("⚙️ Column Mapping", expanded=False):
        num_cols_list = [None] + detect_column_types(ana_df)["numeric"]
        dt_cols_list  = [None] + detect_column_types(ana_df)["datetime"] + \
                        [c for c in ana_df.columns if "date" in c.lower() and c not in detect_column_types(ana_df)["datetime"]]
        cat_cols_list = [None] + detect_column_types(ana_df)["categorical"]

        map_c1, map_c2, map_c3, map_c4 = st.columns(4)
        with map_c1:
            date_sel = st.selectbox(
                "Date column", dt_cols_list,
                index=dt_cols_list.index(default_map["date"]) if default_map["date"] in dt_cols_list else 0,
                key="ana_date",
            )
        with map_c2:
            value_sel = st.selectbox(
                "Value / Revenue column", num_cols_list,
                index=num_cols_list.index(default_map["value"]) if default_map["value"] in num_cols_list else 0,
                key="ana_value",
            )
        with map_c3:
            product_sel = st.selectbox(
                "Product / Category column", cat_cols_list,
                index=cat_cols_list.index(default_map["product"]) if default_map["product"] in cat_cols_list else 0,
                key="ana_product",
            )
        with map_c4:
            region_sel = st.selectbox(
                "Region column", cat_cols_list,
                index=cat_cols_list.index(default_map["region"]) if default_map["region"] in cat_cols_list else 0,
                key="ana_region",
            )

    col_map = {
        "date":    st.session_state.get("ana_date",    default_map["date"]),
        "value":   st.session_state.get("ana_value",   default_map["value"]),
        "product": st.session_state.get("ana_product", default_map["product"]),
        "region":  st.session_state.get("ana_region",  default_map["region"]),
    }
    st.session_state["_analytics_colmap"] = col_map

    # Run analytics
    try:
        ana_report = generate_analytics_report(ana_df, col_map)
        st.session_state["_analytics_report"] = ana_report
        st.session_state["_analytics_df"]     = ana_df
    except Exception as exc:
        st.error(f"Analytics failed: {exc}")
        ana_report = None

    if ana_report:
        from themes import get_layout as _get_layout

        # KPI row
        if ana_report.revenue_profit:
            rp = ana_report.revenue_profit
            rp1, rp2, rp3, rp4 = st.columns(4)
            rp1.metric("Total Revenue",   f"${rp['total_revenue']:,.0f}"  if rp["total_revenue"]  else "N/A")
            rp2.metric("Avg Revenue",     f"${rp['avg_revenue']:,.2f}"    if rp["avg_revenue"]    else "N/A")
            rp3.metric("Median Revenue",  f"${rp['median_revenue']:,.2f}" if rp["median_revenue"] else "N/A")
            rp4.metric("Revenue Std Dev", f"${rp['revenue_std']:,.2f}"    if rp["revenue_std"]    else "N/A")

        if ana_report.growth:
            g    = ana_report.growth
            cagr = g.get("cagr_pct")
            bm   = g.get("best_mom_growth")
            wm   = g.get("worst_mom_growth")
            gc1, gc2, gc3 = st.columns(3)
            gc1.metric("CAGR",            f"{cagr:.1f}%" if cagr is not None else "N/A")
            gc2.metric("Best MoM Growth", f"+{bm['growth_pct']:.1f}% ({bm['period']})" if bm else "N/A")
            gc3.metric("Worst MoM",       f"{wm['growth_pct']:.1f}% ({wm['period']})"  if wm else "N/A")

        st.markdown("<hr>", unsafe_allow_html=True)

        # ── Adaptive multi-chart dashboard ────────────────────────────────────
        st.markdown('<div class="section-label">📊 Auto-Generated Charts</div>', unsafe_allow_html=True)

        adp_cust = {
            "palette":     st.session_state.get("cust_palette", "biswa"),
            "dark_mode":   st.session_state.get("app_theme", "dark") == "dark",
            "top_n":       st.session_state.get("cust_topn", 0),
            "show_labels": st.session_state.get("cust_labels", True),
            "sort_asc":    st.session_state.get("cust_sort", False),
        }

        try:
            adp_panels = generate_adaptive_dashboard(ana_df, col_map, adp_cust)
        except Exception as adp_exc:
            st.warning(f"Auto-dashboard error: {adp_exc}")
            adp_panels = []

        _ADP_BADGE = {
            "kpi": "🔢 KPI", "line": "📈 Line", "bar": "📊 Bar", "pie": "🥧 Pie",
            "scatter": "⚡ Scatter", "histogram": "📉 Histogram",
            "treemap": "🗂️ Treemap", "heatmap": "🔥 Heatmap", "geo": "🗺️ Geo Map",
        }

        # Render 2-per-row
        chart_panels = [p for p in adp_panels if p["chart_type"] != "kpi"]
        kpi_panels   = [p for p in adp_panels if p["chart_type"] == "kpi"]

        # KPI cards first
        for kp in kpi_panels:
            with st.expander(f"🔢 KPI — {kp['title']}", expanded=True):
                kpis = kp.get("kpis", {})
                kpi_keys = list(kpis.keys())
                kpi_vals = list(kpis.values())
                for row_s in range(0, len(kpi_keys), 4):
                    rk = kpi_keys[row_s: row_s + 4]
                    rv = kpi_vals[row_s: row_s + 4]
                    for kc, (k, v) in zip(st.columns(len(rk)), zip(rk, rv)):
                        kc.metric(k, v)

        # Charts in pairs
        for pair in [chart_panels[i:i+2] for i in range(0, len(chart_panels), 2)]:
            g_cols = st.columns(len(pair))
            for gc, panel in zip(g_cols, pair):
                with gc:
                    badge = _ADP_BADGE.get(panel["chart_type"], panel["chart_type"].title())
                    if panel.get("fig") is not None:
                        st.markdown(
                            f'<div class="glass-card">'
                            f'<div class="chart-card-header">'
                            f'<span class="chart-card-title">{panel["title"]}</span>'
                            f'<span class="chart-card-badge">{badge}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        st.plotly_chart(panel["fig"], use_container_width=True, key=f"adp_{panel['panel_id']}")
                        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<hr>", unsafe_allow_html=True)

        # Classic analytics (collapsible)
        st.markdown('<div class="section-label">📋 Detailed Analytics</div>', unsafe_allow_html=True)
        if ana_report.trend:
            with st.expander("📈 Trend Analysis", expanded=False):
                t = ana_report.trend
                tc1, tc2, tc3 = st.columns(3)
                tc1.metric("Overall Trend",     t["overall_trend"].title())
                tc2.metric("Avg Monthly Growth", f"{t['avg_monthly_growth_pct']:.1f}%")
                tc3.metric("Peak Period",         t["peak_period"] or "N/A")

        if ana_report.outliers:
            with st.expander("🔍 Outlier Detection", expanded=False):
                outlier_rows = []
                for col_o, info_o in ana_report.outliers.items():
                    outlier_rows.append({
                        "Column":       col_o,
                        "Method":       info_o["method"].upper(),
                        "# Outliers":   info_o["n_outliers"],
                        "% of Data":    f"{info_o['outlier_pct']:.1f}%",
                        "Normal Range": f"{info_o['lower_bound']:,.2f} – {info_o['upper_bound']:,.2f}",
                    })
                if outlier_rows:
                    st.dataframe(pd.DataFrame(outlier_rows), use_container_width=True, hide_index=True)
                else:
                    st.success("No significant outliers detected.")

        bw_c1, bw_c2 = st.columns(2)
        with bw_c1:
            if ana_report.best_worst_products:
                with st.expander("🏆 Best & Worst Products", expanded=False):
                    bwp      = ana_report.best_worst_products
                    best_df  = pd.DataFrame(bwp.get("best", []))
                    worst_df = pd.DataFrame(bwp.get("worst", []))
                    if not best_df.empty:
                        st.markdown("**Top Performers**")
                        st.dataframe(best_df.rename(columns={"label": "Product", "value": "Revenue", "rank": "Rank"}), use_container_width=True, hide_index=True)
                    if not worst_df.empty:
                        st.markdown("**Bottom Performers**")
                        st.dataframe(worst_df.rename(columns={"label": "Product", "value": "Revenue", "rank": "Rank"}), use_container_width=True, hide_index=True)
        with bw_c2:
            if ana_report.best_worst_regions:
                with st.expander("🌍 Best & Worst Regions", expanded=False):
                    bwr     = ana_report.best_worst_regions
                    best_r  = pd.DataFrame(bwr.get("best", []))
                    worst_r = pd.DataFrame(bwr.get("worst", []))
                    if not best_r.empty:
                        st.markdown("**Top Regions**")
                        st.dataframe(best_r.rename(columns={"label": "Region", "value": "Revenue", "rank": "Rank"}), use_container_width=True, hide_index=True)
                    if not worst_r.empty:
                        st.markdown("**Bottom Regions**")
                        st.dataframe(worst_r.rename(columns={"label": "Region", "value": "Revenue", "rank": "Rank"}), use_container_width=True, hide_index=True)

        if ana_report.growth and ana_report.growth.get("yoy"):
            with st.expander("📊 Year-over-Year Growth", expanded=False):
                st.dataframe(
                    pd.DataFrame(ana_report.growth["yoy"]).rename(
                        columns={"year": "Year", "value": "Revenue", "growth_pct": "Growth %"}
                    ),
                    use_container_width=True, hide_index=True,
                )

        # AI Business Insights
        st.markdown('<div class="section-label">✨ AI Business Insights</div>', unsafe_allow_html=True)
        if st.button("✨ Generate AI Insights", key="gen_ai_insights", type="primary"):
            if not os.environ.get("GROQ_API_KEY", "").strip():
                st.warning("Set your Groq API key in the sidebar to generate AI insights.")
            else:
                with st.spinner("Generating AI insights…"):
                    ai_text = generate_ai_business_insights(ana_report, ana_df)
                    st.session_state["_ai_insights_text"] = ai_text or "Could not generate insights — check your API key."

        ai_text = st.session_state.get("_ai_insights_text", "")
        if ai_text:
            st.markdown(
                f'<div class="glass-card insight-card">'
                f'<div class="insight-title">AI Executive Summary</div>'
                f'<div class="insight-body">{ai_text}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        if ana_report.errors:
            with st.expander("⚠️ Analytics Errors (debug)", expanded=False):
                for k, v in ana_report.errors.items():
                    st.code(f"{k}: {v}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 · RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab_recs:

    st.markdown(
        '<div style="margin-bottom:20px">'
        '<div class="page-title" style="font-size:22px">💡 Recommendation Agent</div>'
        '<div class="page-subtitle">Actionable business recommendations · based on your dataset analytics</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    rec_report = st.session_state.get("_analytics_report")
    rec_df     = st.session_state.get("_analytics_df")
    if rec_df is None: rec_df = full_df

    if rec_report is None:
        st.info(
            "💡 Open the **📊 Analytics** tab first to analyse your dataset, "
            "then come back here for AI-powered recommendations."
        )
    else:
        recs = generate_recommendations(rec_report)

        if not recs:
            st.success("✅ No significant issues detected — your dataset looks healthy!")
        else:
            high_count   = sum(1 for r in recs if r.priority == "high")
            medium_count = sum(1 for r in recs if r.priority == "medium")
            low_count    = sum(1 for r in recs if r.priority == "low")

            rk1, rk2, rk3, rk4 = st.columns(4)
            rk1.metric("Total Recommendations", str(len(recs)))
            rk2.metric("🔴 High Priority",       str(high_count))
            rk3.metric("🟡 Medium Priority",     str(medium_count))
            rk4.metric("🟢 Low Priority",        str(low_count))

            st.markdown("<hr>", unsafe_allow_html=True)

            if high_count > 0:
                if st.button("✨ Enrich High-Priority Recs with AI", key="enrich_recs"):
                    if not os.environ.get("GROQ_API_KEY", "").strip():
                        st.warning("Set your Groq API key in the sidebar first.")
                    else:
                        with st.spinner("AI enriching high-priority recommendations…"):
                            recs = enrich_recommendations_with_llm(recs, rec_df)
                        st.success("Done! High-priority recommendations now include AI narratives.")

            _PRI_COLORS = {
                "high":   ("rgba(239,68,68,0.12)",  "rgba(239,68,68,0.35)",  "#FCA5A5"),
                "medium": ("rgba(245,158,11,0.12)", "rgba(245,158,11,0.35)", "#FCD34D"),
                "low":    ("rgba(16,185,129,0.12)", "rgba(16,185,129,0.35)", "#6EE7B7"),
            }

            for rec in recs:
                bg, border, text = _PRI_COLORS.get(
                    rec.priority, ("rgba(99,102,241,0.1)", "rgba(99,102,241,0.3)", "#818CF8")
                )
                detail_html = (
                    f'<div style="color:var(--text-muted);font-size:13px;margin-top:8px;font-style:italic">'
                    f'{rec.detail}</div>'
                ) if rec.detail else ""
                st.markdown(
                    f'<div style="background:{bg};border:1px solid {border};'
                    f'border-radius:12px;padding:16px 20px;margin-bottom:12px">'
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
                    f'  <span style="font-size:18px">{rec.priority_emoji}</span>'
                    f'  <span style="font-size:12px;font-weight:700;color:{text};'
                    f'text-transform:uppercase;letter-spacing:0.5px">{rec.priority} priority</span>'
                    f'  <span style="font-size:12px;color:var(--text-dim)">·</span>'
                    f'  <span style="font-size:12px;color:var(--text-dim)">{rec.category_emoji} {rec.category}</span>'
                    f'</div>'
                    f'<div style="font-size:14px;color:var(--text);font-weight:600;margin-bottom:4px">📋 Finding</div>'
                    f'<div style="font-size:13px;color:var(--text-muted);margin-bottom:10px">{rec.finding}</div>'
                    f'<div style="font-size:14px;color:var(--text);font-weight:600;margin-bottom:4px">⚡ Action</div>'
                    f'<div style="font-size:13px;color:var(--text-muted);margin-bottom:10px">{rec.action}</div>'
                    f'<div style="font-size:14px;color:var(--text);font-weight:600;margin-bottom:4px">🎯 Impact</div>'
                    f'<div style="font-size:13px;color:var(--text-muted)">{rec.impact}</div>'
                    f'{detail_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            rec_csv = recommendations_to_df(recs).to_csv(index=False).encode()
            st.download_button(
                "⬇️ Download Recommendations CSV",
                data=rec_csv, file_name="recommendations.csv", mime="text/csv",
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 · FORECAST
# ══════════════════════════════════════════════════════════════════════════════
with tab_forecast:

    st.markdown(
        '<div style="margin-bottom:20px">'
        '<div class="page-title" style="font-size:22px">📈 Forecast</div>'
        '<div class="page-subtitle">Sales & revenue forecasting · Linear Regression · ARIMA · Prophet (auto-detected)</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    fc_method = detect_available_forecaster()
    _FC_LABEL = {"prophet": "🔮 Prophet", "arima": "📐 ARIMA", "linear": "📏 Linear Regression"}
    st.markdown(
        f'<div class="dataset-badge">'
        f'Active forecaster: <strong>{_FC_LABEL.get(fc_method, fc_method)}</strong> · '
        f'Install <code>prophet</code> or <code>statsmodels</code> for better accuracy'
        f'</div>',
        unsafe_allow_html=True,
    )

    fc_df = st.session_state.get("_analytics_df")
    if fc_df is None: fc_df = full_df

    fc_ct         = detect_column_types(fc_df)
    fc_all_cols   = list(fc_df.columns)
    fc_date_opts  = fc_ct["datetime"] + [c for c in fc_all_cols if "date" in c.lower() and c not in fc_ct["datetime"]]
    fc_value_opts = fc_ct["numeric"] or fc_all_cols

    fc_c1, fc_c2, fc_c3 = st.columns([2, 2, 1])
    with fc_c1:
        fc_date_col = st.selectbox(
            "Date column",
            fc_date_opts if fc_date_opts else fc_all_cols,
            index=0, key="fc_date",
        )
    with fc_c2:
        default_val     = st.session_state.get("_analytics_colmap", {}).get("value")
        fc_default_idx  = fc_value_opts.index(default_val) if default_val in fc_value_opts else 0
        fc_value_col    = st.selectbox(
            "Value column to forecast",
            fc_value_opts, index=fc_default_idx, key="fc_value",
        )
    with fc_c3:
        fc_periods = st.slider("Periods ahead", 1, 24, 6, key="fc_periods")

    if st.button("🚀 Run Forecast", type="primary", key="fc_run"):
        with st.spinner(f"Forecasting {fc_periods} periods with {_FC_LABEL.get(fc_method, fc_method)}…"):
            fc_result = run_forecast(
                df=fc_df, date_col=fc_date_col,
                value_col=fc_value_col, periods=fc_periods, method="auto",
            )
        st.session_state["_forecast_result"] = fc_result

    fc_result = st.session_state.get("_forecast_result")

    if fc_result:
        if fc_result.error:
            st.error(f"Forecast error: {fc_result.error}")
        else:
            m = fc_result.metrics
            fm1, fm2, fm3 = st.columns(3)
            fm1.metric("Method", _FC_LABEL.get(fc_result.method, fc_result.method))
            fm2.metric("MAPE",   f"{m.get('mape')}%" if m.get("mape") is not None else "N/A")
            fm3.metric(
                "R²" if "r_squared" in m else ("AIC" if "aic" in m else "Periods"),
                str(m.get("r_squared", m.get("aic", fc_result.periods))),
            )

            hist  = fc_result.historical_df
            fcast = fc_result.forecast_df

            _dark_mode = st.session_state.get("app_theme", "dark") == "dark"
            from themes import get_palette as _gp, get_layout as _gl
            _pal    = _gp(st.session_state.get("cust_palette", "biswa"))
            _layout = _gl(dark=_dark_mode, title="")

            fig_fc = go.Figure()
            if hist is not None and not hist.empty:
                fig_fc.add_trace(go.Scatter(
                    x=hist["date"], y=hist["value"],
                    mode="lines+markers", name="Historical",
                    line=dict(color=_pal[0], width=2.5), marker=dict(size=5),
                    hovertemplate="<b>%{x|%Y-%m}</b><br>Actual: %{y:,.2f}<extra></extra>",
                ))
            if fcast is not None and "lower_ci" in fcast.columns:
                fig_fc.add_trace(go.Scatter(
                    x=pd.concat([fcast["date"], fcast["date"].iloc[::-1]]),
                    y=pd.concat([fcast["upper_ci"], fcast["lower_ci"].iloc[::-1]]),
                    fill="toself", fillcolor="rgba(99,102,241,0.15)",
                    line=dict(color="rgba(99,102,241,0)"),
                    name="95% CI", hoverinfo="skip", showlegend=True,
                ))
            if fcast is not None and not fcast.empty:
                fig_fc.add_trace(go.Scatter(
                    x=fcast["date"], y=fcast["predicted"],
                    mode="lines+markers", name="Forecast",
                    line=dict(color=_pal[1] if len(_pal) > 1 else "#22C55E", width=2.5, dash="dash"),
                    marker=dict(size=7, symbol="diamond"),
                    hovertemplate="<b>%{x|%Y-%m}</b><br>Forecast: %{y:,.2f}<extra></extra>",
                ))
            fig_fc.update_layout(
                xaxis_title=fc_date_col, yaxis_title=fc_value_col,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                **_layout,
            )
            st.plotly_chart(fig_fc, use_container_width=True)

            if fcast is not None:
                fc_csv = fcast.to_csv(index=False).encode()
                st.download_button(
                    "⬇️ Download Forecast CSV",
                    data=fc_csv, file_name="forecast.csv", mime="text/csv",
                )
                with st.expander("Forecast Data Table"):
                    st.dataframe(fcast, use_container_width=True, hide_index=True)
