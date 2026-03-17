"""
app.py  (v4  —  PowerBI-style BI Dashboard)
--------------------------------------------
Full layout:

SIDEBAR
  ⚙  Settings (API key)
  🎛  Filters   (region · category · payment · date range)
  🎨  Customize (palette · dark mode · chart type · top-N · labels · sort)
  ⚡  Quick Questions
  🕑  Recent Queries

MAIN AREA  (tabs)
  📊 Dashboard   — multi-chart (primary + pie + trend + table)
                    AI insight · drill-down · export
  🔍 Data Explorer
  ℹ️  About

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
from dashboard       import generate_dashboard, get_drilldown_sql
from themes          import PALETTES

# ─────────────────────────────────────────────────────────────────────────────
# Page config  (MUST be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title = "AI · Business Intelligence",
    page_icon  = "📊",
    layout     = "wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS  — shared styles
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Header ─────────────────────────── */
.bi-header {
    background: linear-gradient(135deg,#667eea 0%,#764ba2 100%);
    padding:1.3rem 2rem; border-radius:14px; color:#fff; margin-bottom:1rem;
}
.bi-header h1 { margin:0; font-size:1.65rem; letter-spacing:-.3px; }
.bi-header p  { margin:.25rem 0 0; opacity:.85; font-size:.88rem; }

/* ── KPI cards ──────────────────────── */
div[data-testid="metric-container"] {
    background:#f8f9ff; border:1px solid #e0e4f5;
    border-radius:10px; padding:.4rem .8rem;
}

/* ── Insight card ───────────────────── */
.insight-card {
    background:linear-gradient(135deg,#f0f4ff 0%,#faf0ff 100%);
    border-left:4px solid #764ba2; border-radius:0 10px 10px 0;
    padding:.9rem 1.2rem; margin:.8rem 0 1rem;
    font-size:.95rem; color:#2d2d4e; line-height:1.7;
}

/* ── Drilldown card ─────────────────── */
.drill-card {
    background:#f0fff4; border-left:4px solid #38a169;
    border-radius:0 10px 10px 0;
    padding:.7rem 1rem; margin:.5rem 0;
    font-size:.88rem; color:#1a4731;
}

/* ── SQL box ─────────────────────────── */
.sql-box {
    background:#1e1e2e; color:#cdd6f4;
    border-radius:8px; padding:.8rem 1rem;
    font-family:'JetBrains Mono','Fira Code',monospace;
    font-size:.8rem; white-space:pre-wrap; word-break:break-all;
}

/* ── Section heading ─────────────────── */
.section-title {
    font-size:1rem; font-weight:700; color:#4a4a7a;
    letter-spacing:.3px; margin:.8rem 0 .4rem;
    text-transform:uppercase;
}

#MainMenu, footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state bootstrap
# ─────────────────────────────────────────────────────────────────────────────
ensure_history()
init_filters()

for key, default in [
    ("last_result",        None),
    ("auto_execute",       False),
    ("prefill_question",   ""),
    ("chart_type_override", None),
    ("drill_result",       None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─────────────────────────────────────────────────────────────────────────────
# Database (cached for session)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading 50 000 rows into database…")
def get_db_connection():
    return init_db()

conn = get_db_connection()

# ─────────────────────────────────────────────────────────────────────────────
# Load full dataset for filters (cached)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_full_df() -> pd.DataFrame:
    return pd.read_csv("dataset.csv", parse_dates=["order_date"])

full_df = load_full_df()

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="bi-header">
  <h1>📊 AI Business Intelligence Dashboard</h1>
  <p>Natural language → multi-chart dashboard · drill-down · live filters · PowerBI-style analytics</p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:

    # ── ⚙️ Settings ──────────────────────────────────────────────────────────
    st.header("⚙️ Settings")
    api_key = st.text_input(
        "Groq API Key", type="password",
        placeholder="gsk_...  (or set GROQ_API_KEY env var)",
        help="Free key at https://console.groq.com",
    )
    if api_key.strip():
        os.environ["GROQ_API_KEY"] = api_key.strip()

    st.divider()

    # ── 🎛️ Filters ───────────────────────────────────────────────────────────
    render_filter_panel(full_df)

    st.divider()

    # ── 🎨 Customize ─────────────────────────────────────────────────────────
    st.subheader("🎨 Customize Charts")

    palette_name = st.selectbox(
        "Color Theme", list(PALETTES.keys()), index=0, key="cust_palette"
    )
    dark_mode = st.toggle("🌙 Dark Mode", value=False, key="cust_dark")

    chart_types = ["auto", "bar", "line", "pie", "area", "scatter", "histogram"]
    manual_type = st.selectbox(
        "Chart Type", chart_types,
        index=0, key="cust_type",
        help="'auto' uses the AI recommendation",
    )

    top_n = st.slider("Top N rows", 0, 30, 0, key="cust_topn",
                      help="0 = show all")
    show_labels = st.toggle("Show Data Labels", value=True, key="cust_labels")
    sort_asc    = st.toggle("Sort Ascending",  value=False, key="cust_sort")

    def get_customization() -> dict:
        return {
            "palette"    : st.session_state.get("cust_palette", "Bold"),
            "dark_mode"  : st.session_state.get("cust_dark", False),
            "top_n"      : st.session_state.get("cust_topn", 0),
            "show_labels": st.session_state.get("cust_labels", True),
            "sort_asc"   : st.session_state.get("cust_sort", False),
        }

    st.divider()

    # ── ⚡ Quick Questions ────────────────────────────────────────────────────
    st.subheader("⚡ Quick Questions")
    st.caption("One click — runs instantly")

    QUICK_QUESTIONS = [
        "What is the total revenue by product category?",
        "Show monthly revenue trend for 2023",
        "Which region generates the most revenue?",
        "Revenue share by payment method",
        "Show average rating per product category",
        "Top 5 categories by quantity sold",
        "Compare average discount by region",
        "Show total revenue by month in 2022",
        "Which payment method has the highest order value?",
        "Revenue breakdown by region and category",
    ]
    for q in QUICK_QUESTIONS:
        if st.button(q, use_container_width=True, key=f"qq_{q}"):
            st.session_state["prefill_question"] = q
            st.session_state["auto_execute"]     = True
            st.rerun()

    st.divider()

    # ── 🕑 History ────────────────────────────────────────────────────────────
    st.subheader("🕑 Recent Queries")
    rerun_q = render_history_sidebar()
    if rerun_q:
        st.session_state["prefill_question"] = rerun_q
        st.session_state["auto_execute"]     = True
        st.rerun()

    st.divider()
    st.subheader("📋 Dataset")
    st.markdown(f"**Table:** `{TABLE_NAME}` · 50 000 rows · 13 cols · 2022–2023")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN TABS
# ─────────────────────────────────────────────────────────────────────────────
tab_dash, tab_explorer, tab_about = st.tabs(
    ["📊 Dashboard", "🔍 Data Explorer", "ℹ️ About"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1  ·  DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:

    prefill      = st.session_state.pop("prefill_question", "")
    auto_execute = st.session_state.pop("auto_execute", False)

    question = st.text_input(
        "question", value=prefill,
        placeholder="e.g. Show revenue by region …",
        label_visibility="collapsed",
        key="q_input",
    )

    col_run, col_clr = st.columns([7, 1])
    with col_run:
        run_btn = st.button("🔍  Generate Dashboard", type="primary",
                            use_container_width=True)
    with col_clr:
        if st.button("🗑️", use_container_width=True, help="Clear"):
            st.session_state["last_result"]  = None
            st.session_state["drill_result"] = None
            st.rerun()

    should_run = (run_btn and question.strip()) or (auto_execute and question.strip())

    # ── API key guard ──────────────────────────────────────────────────────
    def _need_key() -> bool:
        if not os.environ.get("GROQ_API_KEY", "").strip():
            st.error("Set your Groq API key in the sidebar.")
            return True
        return False

    # ── Pipeline ───────────────────────────────────────────────────────────
    if should_run:
        if _need_key():
            st.stop()

        cust    = get_customization()
        where   = get_where_clause()
        flt_ctx = get_filter_summary()

        prog = st.progress(0, text="🤖 Asking Groq…")

        # Stage 1: LLM
        try:
            chart_meta = ask_groq(question, filter_context=flt_ctx)
        except ValueError as e:
            prog.empty(); st.error(f"**LLM Error:** {e}"); st.stop()

        # Stage 2: SQL (inject filters into LLM SQL)
        prog.progress(30, text="🗄️ Running SQL…")
        raw_sql = chart_meta["sql_query"]
        sql     = inject_filters(raw_sql)
        df, err = run_query(conn, sql)

        if err:
            prog.empty()
            st.error(f"**DB Error:** {err}")
            with st.expander("Generated SQL"):
                st.code(sql, language="sql")
            st.stop()

        # Stage 3: Multi-chart dashboard
        prog.progress(55, text="📊 Building charts…")
        try:
            panels = generate_dashboard(conn, df, chart_meta, where, cust)
        except Exception as e:
            prog.empty(); st.error(f"**Chart Error:** {e}"); st.stop()

        # Stage 4: Insight
        prog.progress(82, text="🧠 Generating insight…")
        insight = generate_insight(question, df, chart_meta.get("y_axis", ""))

        prog.progress(100, text="✅ Done!"); prog.empty()

        # Persist
        st.session_state["last_result"] = {
            "question"  : question,
            "chart_meta": chart_meta,
            "df"        : df,
            "panels"    : panels,
            "insight"   : insight,
            "sql"       : sql,
        }
        st.session_state["drill_result"]       = None
        st.session_state["chart_type_override"] = None
        add_to_history(question, chart_meta, df, insight)

    elif run_btn and not question.strip():
        st.warning("Type a question first.")

    # ── Render ─────────────────────────────────────────────────────────────
    result = st.session_state.get("last_result")

    if result:
        cust       = get_customization()
        chart_meta = result["chart_meta"]
        df         = result["df"]
        panels     = result["panels"]
        x_col      = chart_meta["x_axis"]
        y_col      = chart_meta["y_axis"]

        st.success("✅ Dashboard generated!")
        st.markdown(f"### 💬 \"{result['question']}\"")

        # ── Manual chart-type selector ──────────────────────────────────────
        CTYPE_ICONS = {
            "auto": "🤖 Auto", "bar": "📊 Bar", "line": "📈 Line",
            "pie": "🥧 Pie", "area": "🏔 Area",
            "scatter": "⚪ Scatter", "histogram": "📉 Histogram",
        }
        sel_label = st.radio(
            "chart_selector", list(CTYPE_ICONS.values()),
            index=0, horizontal=True, label_visibility="collapsed",
            key="chart_radio",
        )
        override = {v: k for k, v in CTYPE_ICONS.items()}.get(sel_label, "auto")
        override = None if override == "auto" else override

        # ── KPI cards ───────────────────────────────────────────────────────
        stats = get_summary_stats(df, y_col)
        if stats:
            kpi_cols = st.columns(len(stats))
            for col_w, (lbl, val) in zip(kpi_cols, stats.items()):
                col_w.metric(lbl, val)

        st.divider()

        # ── Chart grid ──────────────────────────────────────────────────────
        # Re-build panels if customization or override changed
        if override or cust != st.session_state.get("_last_cust"):
            st.session_state["_last_cust"] = cust
            try:
                cust_for_panels = {**cust}
                panels = generate_dashboard(conn, df, chart_meta,
                                            get_where_clause(), cust_for_panels)
                # Apply override to panel 0 (primary)
                if override and panels:
                    from dashboard import _build, _trim
                    from themes import get_palette
                    palette = get_palette(cust["palette"])
                    df0     = _trim(df.copy(), y_col, cust["top_n"], cust["sort_asc"])
                    panels[0]["fig"] = _build(
                        df0, x_col, y_col, override,
                        palette, cust["dark_mode"],
                        chart_meta.get("title", ""), cust["show_labels"]
                    )
            except Exception:
                pass  # keep existing panels on error

        # Layout: 2 columns for up to 4 panels
        panel_pairs = [panels[i:i+2] for i in range(0, len(panels), 2)]
        for pair in panel_pairs:
            cols = st.columns(len(pair))
            for col_w, panel in zip(cols, pair):
                with col_w:
                    st.plotly_chart(panel["fig"], use_container_width=True,
                                    key=f"chart_{panel['panel_id']}")

        # ── Data table (always shown as last panel) ──────────────────────────
        with st.expander(f"📋 Data Table  ({len(df):,} rows)"):
            st.dataframe(
                df.sort_values(by=y_col, ascending=False)
                  .reset_index(drop=True),
                use_container_width=True, hide_index=True,
            )

        # ── AI Insight ──────────────────────────────────────────────────────
        if result["insight"]:
            st.markdown(
                f'<div class="insight-card">'
                f'<strong>💡 AI Insight</strong><br><br>{result["insight"]}'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # ── Drill-Down ──────────────────────────────────────────────────────
        st.markdown('<p class="section-title">🔍 Drill Down</p>',
                    unsafe_allow_html=True)

        drill_options = df[x_col].dropna().unique().tolist()
        if drill_options:
            drill_col_a, drill_col_b = st.columns([3, 1])
            with drill_col_a:
                selected_val = st.selectbox(
                    f"Pick a {x_col.replace('_',' ')} to drill into",
                    options=["— Select —"] + [str(v) for v in drill_options],
                    key="drill_select",
                )
            with drill_col_b:
                drill_btn = st.button("🔍 Drill", use_container_width=True,
                                      key="drill_go")

            if drill_btn and selected_val != "— Select —":
                drill_info = get_drilldown_sql(
                    x_col, selected_val, y_col, get_where_clause()
                )
                if drill_info:
                    drill_sql, breakdown_col = drill_info
                    drill_df, drill_err = run_query(conn, drill_sql)
                    if drill_err:
                        st.error(f"Drill-down error: {drill_err}")
                    else:
                        from dashboard import _build, _trim
                        from themes import get_palette
                        palette   = get_palette(cust["palette"])
                        drill_df2 = _trim(drill_df.copy(), y_col,
                                          cust["top_n"], cust["sort_asc"])
                        drill_fig = _build(
                            drill_df2, breakdown_col, y_col, "bar",
                            palette, cust["dark_mode"],
                            f"{x_col.replace('_',' ').title()}: {selected_val} → by {breakdown_col.replace('_',' ').title()}",
                            cust["show_labels"],
                        )
                        st.session_state["drill_result"] = {
                            "fig"     : drill_fig,
                            "df"      : drill_df,
                            "label"   : selected_val,
                            "x"       : breakdown_col,
                            "y"       : y_col,
                            "sql"     : drill_sql,
                        }
                else:
                    st.info("No drill-down path defined for this dimension.")

        # Render drill-down result
        dr = st.session_state.get("drill_result")
        if dr:
            st.markdown(
                f'<div class="drill-card">'
                f'Drilled into <strong>{dr["label"]}</strong> → '
                f'breakdown by <strong>{dr["x"].replace("_"," ")}</strong>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.plotly_chart(dr["fig"], use_container_width=True, key="drill_chart")
            with st.expander("Drill-Down Data"):
                st.dataframe(dr["df"], use_container_width=True, hide_index=True)
            with st.expander("Drill-Down SQL"):
                st.code(dr["sql"], language="sql")

        st.divider()

        # ── Export + SQL ─────────────────────────────────────────────────────
        if panels:
            render_export_row(df, panels[0]["fig"], chart_meta, result["question"])

        with st.expander("🔎 Generated SQL"):
            st.markdown(f'<div class="sql-box">{result["sql"]}</div>',
                        unsafe_allow_html=True)

        with st.expander("🧠 LLM Decision"):
            st.table(pd.DataFrame([{
                "Title"     : chart_meta.get("title", ""),
                "Chart Type": chart_meta.get("chart_type", ""),
                "X Axis"    : chart_meta.get("x_axis", ""),
                "Y Axis"    : chart_meta.get("y_axis", ""),
            }]))

    elif not should_run:
        st.markdown("""
        <div style="text-align:center;padding:3rem 1rem;color:#999">
          <div style="font-size:4rem">📊</div>
          <h3 style="color:#666;margin-top:.5rem">Ready for your question</h3>
          <p>Type a question above, or tap a <strong>Quick Question</strong>
             in the sidebar to generate your dashboard instantly.</p>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2  ·  DATA EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
with tab_explorer:
    st.subheader("🔍 Explore the Raw Dataset")
    st.caption("Browse, filter and search all 50 000 rows.")

    with st.expander("🎛️ Filters", expanded=True):
        fe1, fe2, fe3, fe4 = st.columns(4)
        with fe1:
            sel_cat = st.selectbox("Category",
                ["All"] + sorted(full_df["product_category"].unique()),
                key="ex_cat")
        with fe2:
            sel_reg = st.selectbox("Region",
                ["All"] + sorted(full_df["customer_region"].unique()),
                key="ex_reg")
        with fe3:
            sel_pay = st.selectbox("Payment",
                ["All"] + sorted(full_df["payment_method"].unique()),
                key="ex_pay")
        with fe4:
            lo = float(full_df["total_revenue"].min())
            hi = float(full_df["total_revenue"].max())
            rev_range = st.slider("Revenue", lo, hi, (lo, hi), step=50.0, key="ex_rev")

    flt = full_df.copy()
    if sel_cat != "All": flt = flt[flt["product_category"] == sel_cat]
    if sel_reg != "All": flt = flt[flt["customer_region"]  == sel_reg]
    if sel_pay != "All": flt = flt[flt["payment_method"]   == sel_pay]
    flt = flt[(flt["total_revenue"] >= rev_range[0]) & (flt["total_revenue"] <= rev_range[1])]

    srch = st.text_input("🔎 Search", placeholder="Books, Asia, UPI…", key="ex_srch")
    if srch.strip():
        mask = flt.astype(str).apply(
            lambda c: c.str.contains(srch.strip(), case=False, na=False)
        ).any(axis=1)
        flt = flt[mask]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rows",          f"{len(flt):,}")
    m2.metric("Total Revenue", f"${flt['total_revenue'].sum():,.0f}")
    m3.metric("Avg Rating",    f"{flt['rating'].mean():.2f}" if len(flt) else "—")
    m4.metric("Avg Discount",  f"{flt['discount_percent'].mean():.1f}%" if len(flt) else "—")

    st.divider()

    dcols = ["order_id","order_date","product_category","customer_region",
             "quantity_sold","total_revenue","rating"]
    sel_cols = st.multiselect("Columns", list(full_df.columns), default=dcols, key="ex_cols")
    st.dataframe(flt[sel_cols or list(full_df.columns)].reset_index(drop=True),
                 use_container_width=True, hide_index=True, height=450)

    st.download_button(
        "⬇️ Download CSV",
        data=flt[sel_cols or list(full_df.columns)].to_csv(index=False).encode(),
        file_name="filtered_data.csv", mime="text/csv",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3  ·  ABOUT
# ══════════════════════════════════════════════════════════════════════════════
with tab_about:
    st.subheader("ℹ️ About this dashboard")
    cl, cr = st.columns([3, 2])

    with cl:
        st.markdown("""
### Architecture

```
User question
      │
      ▼
  Filters (sidebar) ──► filter context hint for LLM
      │
      ▼
  Groq LLM  ──►  JSON { sql, chart_type, x, y, title }
                   │
           inject_filters(sql)
                   │
                   ▼
            SQLite execution
                   │
                   ▼
         pandas DataFrame
                   │
         generate_dashboard()
           │       │        │
        Bar/Pie  Trend   (more panels)
           │       │        │
           └───────┴────────┘
                   │
         Groq AI Insight
                   │
                   ▼
       KPIs · Charts · Insight
       Drill-down · Exports
```

### Files
| File | Role |
|---|---|
| `app.py` | Streamlit UI, orchestration |
| `llm.py` | Groq API + JSON parsing |
| `database.py` | SQLite + safe queries |
| `dashboard.py` | Multi-chart generator + drill-down |
| `chart_generator.py` | Single chart builder |
| `filters.py` | Filter panel + SQL injection |
| `themes.py` | Colour palettes + layouts |
| `insights.py` | AI insight writer |
| `history.py` | Query history |
| `exports.py` | CSV/PNG/JSON downloads |
        """)

    with cr:
        st.markdown("""
### Tech stack
| Layer | Technology |
|---|---|
| UI | Streamlit |
| LLM | Groq · llama-3.3-70b-versatile |
| Charts | Plotly Express |
| Data | pandas |
| DB | SQLite (stdlib) |

### Colour themes
| Theme | Description |
|---|---|
| Bold | High-contrast default |
| Vivid | Saturated modern |
| Pastel | Soft presentation |
| Dark24 | 24 distinct dark hues |
| Set3 | Colorbrewer Set3 |
| Neon | Electric glow palette |

### Chart types
Bar · Line · Pie/Donut · Area · Scatter · Histogram

### Dataset
50 000 orders · 13 columns · 2022–2023
Categories: Books, Fashion, Sports, Beauty,
Electronics, Home & Kitchen
Regions: North America, Asia, Europe, Middle East
        """)
