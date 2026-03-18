"""
app.py  (v6 — Final GitHub Release)
-------------------------------------
Premium AI-powered BI dashboard. Production-ready.

New in v6
  ✦ Dark / Light theme toggle (top toolbar, persisted in session state)
  ✦ Anomaly detection panel (z-score, shown after AI insight)
  ✦ Follow-up / Click-to-Ask suggestion chips (context-aware)
  ✦ BI colour palette as default (#6366F1 family)
  ✦ Plotly chart font auto-adapts to page theme
  ✦ Sidebar reorganised: Analytics · Chart Style · Data Controls · Filters
  ✦ All previous features preserved unchanged

Run:
    streamlit run app.py
"""

import os
import streamlit as st
import pandas as pd

from database        import init_db, run_query, TABLE_NAME
from llm             import ask_groq
from chart_generator import build_chart, get_summary_stats
from insights        import generate_insight
from history         import ensure_history, add_to_history, render_history_sidebar
from exports         import render_export_row
from filters         import init_filters, render_filter_panel, get_where_clause, \
                            inject_filters, get_filter_summary
from dashboard       import generate_dashboard, get_drilldown_sql, can_drilldown, \
                            _build as _dash_build, _trim as _dash_trim
from themes          import PALETTES, get_palette
from _css            import get_css
from anomaly         import detect_anomalies, format_anomaly_html, get_followup_suggestions

# ── Page config (MUST be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title            = "BI Intelligence",
    page_icon             = "📊",
    layout                = "wide",
    initial_sidebar_state = "expanded",
)

# ── Session state bootstrap ───────────────────────────────────────────────────
ensure_history()
init_filters()
_DEFAULTS = [
    ("app_theme",          "dark"),
    ("last_result",         None),
    ("auto_execute",        False),
    ("prefill_question",    ""),
    ("chart_type_override", None),
    ("drill_result",        None),
    ("_last_cust",          None),
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
    # Chart dark mode defaults to match the page theme
    page_dark = st.session_state.get("app_theme", "dark") == "dark"
    return {
        "palette"    : st.session_state.get("cust_palette", "BI"),
        "dark_mode"  : st.session_state.get("cust_dark",    page_dark),
        "top_n"      : st.session_state.get("cust_topn",    0),
        "show_labels": st.session_state.get("cust_labels",  True),
        "sort_asc"   : st.session_state.get("cust_sort",    False),
    }

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:

    # Brand
    st.markdown(
        '<div class="sb-brand">'
        '<div class="sb-brand-icon">📊</div>'
        '<div><div class="sb-brand-name">BI Intelligence</div>'
        '<div class="sb-brand-sub">AI-Powered Analytics</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── API key ───────────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section-label">API Configuration</div>',
                unsafe_allow_html=True)
    api_key = st.text_input(
        "Groq API Key", type="password",
        placeholder="gsk_...  (or set GROQ_API_KEY env var)",
        label_visibility="collapsed",
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

    # ── Analytics quick questions ─────────────────────────────────────────────
    st.markdown('<div class="sb-section-label">📈 Analytics</div>',
                unsafe_allow_html=True)

    QUICK_ANALYTICS = [
        ("📊", "Revenue by product category"),
        ("🌍", "Revenue by customer region"),
        ("📅", "Monthly revenue trend 2023"),
        ("💳", "Revenue share by payment method"),
        ("⭐", "Average rating per category"),
        ("📦", "Top 5 categories by quantity sold"),
        ("💰", "Average discount percentage by region"),
        ("🗓",  "Total revenue by month in 2022"),
        ("🏆", "Highest average order value by payment method"),
        ("🔀", "Revenue breakdown by region and category"),
    ]
    for icon, q in QUICK_ANALYTICS:
        if st.button(f"{icon}  {q}", use_container_width=True, key=f"qq_{q}"):
            st.session_state["prefill_question"] = q
            st.session_state["auto_execute"]     = True
            st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Chart Style ───────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section-label">🎨 Chart Style</div>',
                unsafe_allow_html=True)
    st.selectbox(
        "Color Theme", list(PALETTES.keys()), index=0,
        key="cust_palette", label_visibility="collapsed",
    )
    cs1, cs2 = st.columns(2)
    with cs1:
        dark_default = st.session_state.get("app_theme", "dark") == "dark"
        st.toggle("Dark Charts",  value=dark_default, key="cust_dark")
    with cs2:
        st.toggle("Data Labels",  value=True,  key="cust_labels")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Data Controls ─────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section-label">🎛 Data Controls</div>',
                unsafe_allow_html=True)
    st.slider("Top N  (0 = show all)", 0, 30, 0, key="cust_topn")
    st.toggle("Sort Ascending", value=False, key="cust_sort")

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Filters ───────────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section-label">🔍 Filters</div>',
                unsafe_allow_html=True)
    render_filter_panel(full_df)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Recent queries ────────────────────────────────────────────────────────
    st.markdown('<div class="sb-section-label">🕑 Recent Queries</div>',
                unsafe_allow_html=True)
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
# PAGE TITLE BAR  (with theme toggle)
# ─────────────────────────────────────────────────────────────────────────────
tc_left, tc_right = st.columns([7, 1])
with tc_left:
    st.markdown(
        '<div style="padding-bottom:20px;border-bottom:1px solid var(--border);margin-bottom:24px">'
        '<div class="page-title">Business Intelligence</div>'
        '<div class="page-subtitle">Natural language → instant charts · drill-down · live filters · anomaly detection</div>'
        '</div>',
        unsafe_allow_html=True,
    )
with tc_right:
    is_dark = (theme == "dark")
    toggle_label = "☀ Light" if is_dark else "🌙 Dark"
    if st.button(toggle_label, key="theme_toggle", help="Switch theme"):
        st.session_state["app_theme"] = "light" if is_dark else "dark"
        st.rerun()
    st.markdown(
        '<div style="text-align:center;margin-top:4px">'
        '<span style="font-size:10px;color:var(--text-dim)">'
        + ("Dark Mode" if is_dark else "Light Mode") +
        '</span></div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_dash, tab_explorer, tab_about = st.tabs(
    ["  📊  Dashboard  ", "  🔍  Data Explorer  ", "  ℹ️  About  "]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 · DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:

    prefill      = st.session_state.pop("prefill_question", "")
    auto_execute = st.session_state.pop("auto_execute",     False)

    # ── Query bar ─────────────────────────────────────────────────────────────
    st.markdown('<div class="query-bar-wrapper">', unsafe_allow_html=True)
    st.markdown(
        '<div class="query-bar-label">✦ Ask a Business Question</div>',
        unsafe_allow_html=True,
    )
    qcol, bcol, xcol = st.columns([7, 1.6, 0.6])
    with qcol:
        question = st.text_input(
            "q", value=prefill,
            placeholder="Ask a business question…  e.g. revenue by category, monthly trends, top products",
            label_visibility="collapsed",
            key="q_input",
        )
    with bcol:
        run_btn = st.button(
            "⚡  Analyze Data", type="primary", use_container_width=True
        )
    with xcol:
        if st.button("✕", use_container_width=True, help="Clear dashboard"):
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

        # Loading card
        pc = st.empty()
        STEPS = [
            "① Sending question to Groq LLM (llama-3.3-70b-versatile)…",
            "② Running SQL query on 50 000-row dataset…",
            "③ Building multi-chart dashboard panels…",
            "④ Generating AI business insight…",
        ]

        def _show_step(i: int) -> None:
            pc.markdown(
                f'<div class="chart-card" style="margin-bottom:16px">'
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

        # Stage 1 — LLM
        try:
            chart_meta = ask_groq(question, filter_context=flt_ctx)
        except ValueError as e:
            prog.empty(); pc.empty()
            st.error(f"**LLM Error:** {e}"); st.stop()

        prog.progress(30); _show_step(1)

        # Stage 2 — SQL
        sql     = inject_filters(chart_meta["sql_query"])
        df, err = run_query(conn, sql)
        if err:
            prog.empty(); pc.empty()
            st.error(f"**Database Error:** {err}")
            with st.expander("Generated SQL (debug)"):
                st.code(sql, language="sql")
            st.stop()

        prog.progress(60); _show_step(2)

        # Stage 3 — Charts
        try:
            panels = generate_dashboard(conn, df, chart_meta, where, cust)
        except Exception as e:
            prog.empty(); pc.empty()
            st.error(f"**Chart Error:** {e}"); st.stop()

        prog.progress(82); _show_step(3)

        # Stage 4 — Insight (non-blocking)
        insight = generate_insight(question, df, chart_meta.get("y_axis", ""))

        # Anomaly detection
        x_col = chart_meta.get("x_axis", "")
        y_col = chart_meta.get("y_axis", "")
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

        # ── Status + question echo ────────────────────────────────────────────
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">'
            f'<span style="font-size:12px;color:var(--success);background:rgba(16,185,129,.1);'
            f'border:1px solid rgba(16,185,129,.2);border-radius:20px;padding:3px 10px;font-weight:500">'
            f'✓ Dashboard Ready</span>'
            f'<span style="font-size:13px;color:var(--text-muted)">'
            f'<em>{result["question"]}</em></span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Chart-type switcher ───────────────────────────────────────────────
        CTYPE_MAP = {
            "🤖 Auto"       : None,
            "📊 Bar"        : "bar",
            "📈 Line"       : "line",
            "🥧 Pie"        : "pie",
            "🏔 Area"       : "area",
            "⚪ Scatter"    : "scatter",
            "📉 Histogram"  : "histogram",
        }
        sel_label = st.radio(
            "ct", list(CTYPE_MAP.keys()),
            index=0, horizontal=True,
            label_visibility="collapsed",
            key="chart_radio",
        )
        override = CTYPE_MAP.get(sel_label)

        # ── KPI metric row ────────────────────────────────────────────────────
        stats = get_summary_stats(df, y_col)
        if stats:
            ICONS = {
                "Total"  : "💰",
                "Average": "📊",
                "Max"    : "⬆",
                "Min"    : "⬇",
                "Rows"   : "📄",
            }
            kpi_cols = st.columns(len(stats))
            for col_w, (lbl, val) in zip(kpi_cols, stats.items()):
                col_w.metric(f"{ICONS.get(lbl, '')} {lbl}", val)

        st.markdown('<div style="margin-top:8px"></div>', unsafe_allow_html=True)

        # ── Rebuild panels on override or customization change ────────────────
        if override is not None or cust != st.session_state.get("_last_cust"):
            st.session_state["_last_cust"] = cust
            try:
                panels = generate_dashboard(
                    conn, df, chart_meta, get_where_clause(), cust
                )
                if override and panels:
                    pal = get_palette(cust["palette"])
                    d0  = _dash_trim(
                        df.copy(), y_col, cust["top_n"], cust["sort_asc"]
                    )
                    panels[0]["fig"] = _dash_build(
                        d0, x_col, y_col, override, pal,
                        cust["dark_mode"], "",
                        cust["show_labels"],
                    )
            except Exception:
                pass   # keep existing panels on error

        # ── 2-column chart grid ───────────────────────────────────────────────
        CT_BADGE = {
            "bar"       : "Bar",
            "line"      : "Line",
            "pie"       : "Pie",
            "area"      : "Area",
            "scatter"   : "Scatter",
            "histogram" : "Histogram",
            "trend"     : "Trend",
            "companion" : "Share",
            "primary"   : "Chart",
        }
        for pair in [panels[i:i+2] for i in range(0, len(panels), 2)]:
            grid_cols = st.columns(len(pair))
            for gc, panel in zip(grid_cols, pair):
                with gc:
                    badge = CT_BADGE.get(panel["panel_id"], panel["panel_id"].title())
                    st.markdown(
                        f'<div class="chart-card">'
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

        # ── Data table ────────────────────────────────────────────────────────
        with st.expander(f"📋  Data Table  ({len(df):,} rows)"):
            st.dataframe(
                df.sort_values(by=y_col, ascending=False).reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
            )

        # ── AI Insight ────────────────────────────────────────────────────────
        if result["insight"]:
            st.markdown(
                f'<div class="insight-card">'
                f'<div class="insight-title">💡 AI Insight</div>'
                f'<div class="insight-body">{result["insight"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Anomaly Detection ─────────────────────────────────────────────────
        if anomalies:
            items_html = "".join(
                f'<div class="anomaly-item">{format_anomaly_html(a, y_col)}</div>'
                for a in anomalies
            )
            st.markdown(
                f'<div class="anomaly-card">'
                f'<div class="anomaly-title">⚠ Anomaly Detection — {len(anomalies)} unusual value{"s" if len(anomalies) > 1 else ""} found</div>'
                f'{items_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Follow-up / Click-to-Ask suggestions ─────────────────────────────
        suggestions = get_followup_suggestions(x_col, y_col)
        if suggestions:
            st.markdown(
                '<div class="followup-card">'
                '<div class="followup-title">🔍 Explore Further</div>',
                unsafe_allow_html=True,
            )
            sug_cols = st.columns(len(suggestions))
            for sc, (icon, q) in zip(sug_cols, suggestions):
                with sc:
                    if st.button(
                        f"{icon}  {q}", use_container_width=True,
                        key=f"sug_{q[:40]}"
                    ):
                        st.session_state["prefill_question"] = q
                        st.session_state["auto_execute"]     = True
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Drill-Down ────────────────────────────────────────────────────────
        st.markdown(
            '<div class="section-label"><span>🔍</span> Drill-Down Analysis</div>',
            unsafe_allow_html=True,
        )

        if not can_drilldown(x_col):
            st.markdown(
                '<div style="font-size:13px;color:var(--text-dim);padding:8px 0">'
                'ℹ No deeper dimension available for this chart type. '
                'Drill-down works on categorical dimensions: '
                '<strong>region</strong>, <strong>category</strong>, '
                '<strong>payment method</strong>.'
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
                    key="drill_select",
                    label_visibility="collapsed",
                )
            with db_:
                drill_btn = st.button(
                    "🔍  Drill In",
                    use_container_width=True,
                    key="drill_go",
                )

            if drill_btn and sv != "— Select a value —":
                dinfo = get_drilldown_sql(x_col, sv, y_col, get_where_clause())
                if dinfo:
                    dsql, bc = dinfo
                    ddf, derr = run_query(conn, dsql)
                    if derr:
                        st.error(f"Drill error: {derr}")
                    else:
                        pal  = get_palette(cust["palette"])
                        ddf2 = _dash_trim(
                            ddf.copy(), y_col, cust["top_n"], cust["sort_asc"]
                        )
                        dfig = _dash_build(
                            ddf2, bc, y_col, "bar", pal,
                            cust["dark_mode"],
                            "",
                            cust["show_labels"],
                        )
                        st.session_state["drill_result"] = {
                            "fig"  : dfig,
                            "df"   : ddf,
                            "label": sv,
                            "x"    : bc,
                            "y"    : y_col,
                            "sql"  : dsql,
                        }
                else:
                    st.info("No drill-down path defined for this dimension.")

        dr = st.session_state.get("drill_result")
        if dr:
            st.markdown(
                f'<div class="drill-card">'
                f'✓ Drilled into <strong>{dr["label"]}</strong> → '
                f'breakdown by <strong>{dr["x"].replace("_"," ").title()}</strong>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="chart-card">', unsafe_allow_html=True)
            st.plotly_chart(dr["fig"], use_container_width=True, key="drill_chart")
            st.markdown("</div>", unsafe_allow_html=True)

            dd1, dd2 = st.columns(2)
            with dd1:
                with st.expander("📄 Drill-Down Data"):
                    st.dataframe(
                        dr["df"], use_container_width=True, hide_index=True
                    )
            with dd2:
                with st.expander("🔎 Drill-Down SQL"):
                    st.markdown(
                        f'<div class="sql-card">'
                        f'<div class="sql-card-header">SQL Query</div>'
                        f'<div class="sql-card-body">{dr["sql"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # ── Export & Details ──────────────────────────────────────────────────
        st.markdown(
            '<div class="section-label"><span>⬇️</span> Export &amp; Details</div>',
            unsafe_allow_html=True,
        )
        if panels:
            render_export_row(df, panels[0]["fig"], chart_meta, result["question"])

        ex1, ex2 = st.columns(2)
        with ex1:
            with st.expander("🔎  Generated SQL Query"):
                st.markdown(
                    f'<div class="sql-card">'
                    f'<div class="sql-card-header">SQLite · Auto-generated</div>'
                    f'<div class="sql-card-body">{result["sql"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        with ex2:
            with st.expander("🧠  LLM Decision"):
                m = chart_meta
                st.table(pd.DataFrame([{
                    "Title"     : m.get("title", ""),
                    "Chart Type": m.get("chart_type", ""),
                    "X Axis"    : m.get("x_axis", ""),
                    "Y Axis"    : m.get("y_axis", ""),
                }]))

    elif not should_run:
        # ── Empty state ───────────────────────────────────────────────────────
        st.markdown(
            """
            <div class="empty-state">
              <div class="empty-icon">📊</div>
              <div class="empty-title">Your Dashboard Awaits</div>
              <div class="empty-sub">
                Type a business question above — or click a <strong>Quick Analysis</strong>
                shortcut in the sidebar. The AI generates a full multi-chart dashboard,
                AI insight, and anomaly detection in seconds.
              </div>
              <div style="margin-top:28px">
                <span class="chip">📊 Revenue by category</span>
                <span class="chip">📈 Monthly trends</span>
                <span class="chip">🌍 Regional analysis</span>
                <span class="chip">💳 Payment insights</span>
                <span class="chip">⚠ Spot anomalies</span>
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
        '<div class="page-title" style="font-size:18px">Data Explorer</div>'
        '<div class="page-subtitle">Filter, search, and export all 50 000 rows</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.expander("🎛️  Filter Controls", expanded=True):
        fe1, fe2, fe3, fe4 = st.columns(4)
        with fe1:
            sel_cat = st.selectbox(
                "Category",
                ["All"] + sorted(full_df["product_category"].unique()),
                key="ex_cat",
            )
        with fe2:
            sel_reg = st.selectbox(
                "Region",
                ["All"] + sorted(full_df["customer_region"].unique()),
                key="ex_reg",
            )
        with fe3:
            sel_pay = st.selectbox(
                "Payment Method",
                ["All"] + sorted(full_df["payment_method"].unique()),
                key="ex_pay",
            )
        with fe4:
            lo = float(full_df["total_revenue"].min())
            hi = float(full_df["total_revenue"].max())
            rev_range = st.slider(
                "Revenue Range", lo, hi, (lo, hi), step=50.0, key="ex_rev"
            )

    flt = full_df.copy()
    if sel_cat != "All": flt = flt[flt["product_category"] == sel_cat]
    if sel_reg != "All": flt = flt[flt["customer_region"]  == sel_reg]
    if sel_pay != "All": flt = flt[flt["payment_method"]   == sel_pay]
    flt = flt[
        (flt["total_revenue"] >= rev_range[0]) &
        (flt["total_revenue"] <= rev_range[1])
    ]

    srch = st.text_input(
        "🔎  Search all columns",
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

    dcols = [
        "order_id", "order_date", "product_category",
        "customer_region", "quantity_sold", "total_revenue", "rating",
    ]
    sel_cols = st.multiselect(
        "Visible Columns", list(full_df.columns), default=dcols, key="ex_cols"
    )
    st.dataframe(
        flt[sel_cols or list(full_df.columns)].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        height=460,
    )
    st.download_button(
        "⬇️  Download Filtered CSV",
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
        '<div class="page-title" style="font-size:18px">About</div>'
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
| `dashboard.py` | Multi-chart + drill-down |
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
| Background | `#0B1220` | `#F8FAFC` |
| Card | `#111827` | `#FFFFFF` |
| Border | `#1F2937` | `#E5E7EB` |
| Primary | `#6366F1` | `#6366F1` |
| Success | `#10B981` | `#059669` |
| Warning | `#F59E0B` | `#D97706` |
| Font | Inter | Inter |

### BI Colour Palette (default)
`#6366F1` · `#22C55E` · `#F59E0B`
`#EF4444` · `#06B6D4` · `#A855F7`

### Chart types
Bar · Line · Pie/Donut · Area · Scatter · Histogram

### Anomaly detection
Z-score threshold: ±2.0σ · max 3 alerts

### Dataset
50 000 orders · 13 columns · 2022–2023
Categories: Books · Fashion · Sports
Beauty · Electronics · Home & Kitchen
Regions: N. America · Asia · Europe · Middle East
        """)
