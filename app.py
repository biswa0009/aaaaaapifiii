"""
app.py  (v2)
------------
Conversational BI Dashboard — Streamlit entry point.

New in v2
  ✦ Tabbed layout: Dashboard | Data Explorer | About
  ✦ AI-generated plain-English insights (insights.py)
  ✦ Session-based query history with re-run (history.py)
  ✦ CSV / PNG / JSON export buttons (exports.py)
  ✦ Data Explorer: filterable, searchable raw-data browser

Run with:
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

# ─────────────────────────────────────────────────────────────────────────────
# Page config  (must be the FIRST Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title = "BI Dashboard · AI-Powered",
    page_icon  = "📊",
    layout     = "wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Header gradient ─────────────────────────────────────── */
.main-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.4rem 2rem;
    border-radius: 14px;
    color: white;
    margin-bottom: 1.2rem;
}
.main-header h1 { margin: 0; font-size: 1.7rem; letter-spacing: -0.3px; }
.main-header p  { margin: 0.3rem 0 0; opacity: 0.85; font-size: 0.9rem; }

/* ── KPI metric cards ────────────────────────────────────── */
div[data-testid="metric-container"] {
    background: #f8f9ff;
    border: 1px solid #e0e4f5;
    border-radius: 10px;
    padding: 0.4rem 0.8rem;
}

/* ── Insight card ────────────────────────────────────────── */
.insight-card {
    background: linear-gradient(135deg, #f0f4ff 0%, #faf0ff 100%);
    border-left: 4px solid #764ba2;
    border-radius: 0 10px 10px 0;
    padding: 0.9rem 1.2rem;
    margin: 0.8rem 0 1rem;
    font-size: 0.97rem;
    color: #2d2d4e;
    line-height: 1.65;
}

/* ── SQL box ─────────────────────────────────────────────── */
.sql-box {
    background: #1e1e2e;
    color: #cdd6f4;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.82rem;
    white-space: pre-wrap;
    word-break: break-all;
}

/* ── Hide Streamlit chrome ───────────────────────────────── */
#MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state bootstrap
# ─────────────────────────────────────────────────────────────────────────────
ensure_history()

# ─────────────────────────────────────────────────────────────────────────────
# Database  (cached across reruns for the whole session)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading 50,000 rows into database…")
def get_db_connection():
    return init_db()

conn = get_db_connection()

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>📊 Conversational BI Dashboard</h1>
  <p>Ask a business question in plain English — get an instant interactive chart, AI insight, and export.</p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:

    # API key
    st.header("Settings")
    api_key_input = st.text_input(
        "Groq API Key",
        type        = "password",
        placeholder = "gsk_...  (or set GROQ_API_KEY env var)",
        help        = "Free key at https://console.groq.com",
    )
    if api_key_input.strip():
        os.environ["GROQ_API_KEY"] = api_key_input.strip()

    st.divider()

    # Example questions
    st.subheader("Example Questions")
    example_questions = [
        "What is the total revenue by product category?",
        "Show monthly revenue trend for 2023",
        "Which region generates the most revenue?",
        "What is the revenue share by payment method?",
        "Show average rating per product category",
        "What are the top 5 categories by quantity sold?",
        "Compare average discount percentage by region",
        "Show total revenue by month in 2022",
        "Which payment method has the highest average order value?",
        "What is the average quantity sold per product category?",
    ]
    for eq in example_questions:
        if st.button(eq, use_container_width=True, key=f"ex_{eq}"):
            st.session_state["prefill_question"] = eq

    st.divider()

    # Query history
    st.subheader("Recent Queries")
    rerun_q = render_history_sidebar()
    if rerun_q:
        st.session_state["prefill_question"] = rerun_q

    st.divider()

    # Dataset info
    st.subheader("Dataset Info")
    st.markdown(f"""
- **Table:** `{TABLE_NAME}`
- **Rows:** 50,000
- **Columns:** 13
- **Period:** 2022 – 2023
    """)

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────
tab_dash, tab_explorer, tab_about = st.tabs(
    ["📊 Dashboard", "🔍 Data Explorer", "ℹ️ About"]
)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1  ·  DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:

    prefill = st.session_state.pop("prefill_question", "")

    question = st.text_input(
        label            = "Ask a business question",
        value            = prefill,
        placeholder      = "e.g. What is the total revenue by product category?",
        label_visibility = "collapsed",
        key              = "question_input",
    )

    col_ask, col_clear = st.columns([6, 1])
    with col_ask:
        ask_btn = st.button(
            "🔍  Generate Chart", type="primary", use_container_width=True
        )
    with col_clear:
        if st.button("🗑️", use_container_width=True, help="Clear input"):
            st.rerun()

    # Guard: API key present?
    def _check_api_key() -> bool:
        if not os.environ.get("GROQ_API_KEY", "").strip():
            st.error(
                "No Groq API key found. "
                "Paste it in the sidebar or set the GROQ_API_KEY environment variable."
            )
            return False
        return True

    # ── Main generation flow ──────────────────────────────────────────────────
    if ask_btn and question.strip():

        if not _check_api_key():
            st.stop()

        # 4-stage progress bar
        progress = st.progress(0, text="Sending question to Groq…")

        # Stage 1 – LLM
        try:
            chart_meta = ask_groq(question)
        except ValueError as e:
            progress.empty()
            st.error(f"**LLM Error:** {e}")
            st.stop()

        progress.progress(40, text="Executing SQL on dataset…")

        # Stage 2 – SQL
        sql_query  = chart_meta["sql_query"]
        df, db_err = run_query(conn, sql_query)

        if db_err:
            progress.empty()
            st.error(f"**Database Error:** {db_err}")
            with st.expander("Generated SQL (debug)"):
                st.code(sql_query, language="sql")
            st.stop()

        progress.progress(70, text="Building Plotly chart…")

        # Stage 3 – Chart
        try:
            fig = build_chart(df, chart_meta)
        except ValueError as e:
            progress.empty()
            st.error(f"**Chart Error:** {e}")
            with st.expander("Raw query result"):
                st.dataframe(df)
            st.stop()

        progress.progress(85, text="Generating AI insight…")

        # Stage 4 – Insight (non-blocking)
        insight = generate_insight(question, df, chart_meta.get("y_axis", ""))

        progress.progress(100, text="Done!")
        progress.empty()

        # Persist to session history
        add_to_history(question, chart_meta, df, insight)

        # ── Render results ────────────────────────────────────────────────────
        st.success("Chart generated successfully!")
        st.markdown(f"### \"{question}\"")

        # KPI metrics row
        stats = get_summary_stats(df, chart_meta.get("y_axis", ""))
        if stats:
            kpi_cols = st.columns(len(stats))
            for col_w, (label, val) in zip(kpi_cols, stats.items()):
                col_w.metric(label, val)

        st.divider()

        # Interactive chart
        st.plotly_chart(fig, use_container_width=True)

        # AI insight card
        if insight:
            st.markdown(
                f'<div class="insight-card">'
                f'<strong>AI Insight</strong><br><br>{insight}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Export buttons
        render_export_row(df, fig, chart_meta, question)

        # Collapsible debug sections
        with st.expander("Generated SQL"):
            st.markdown(
                f'<div class="sql-box">{sql_query}</div>',
                unsafe_allow_html=True,
            )

        with st.expander(f"Raw Data  ({len(df):,} rows)"):
            st.dataframe(df, use_container_width=True, hide_index=True)

        with st.expander("LLM Decision"):
            st.table(pd.DataFrame([{
                "Chart Type": chart_meta["chart_type"],
                "X Axis"    : chart_meta["x_axis"],
                "Y Axis"    : chart_meta["y_axis"],
            }]))

    elif ask_btn and not question.strip():
        st.warning("Please enter a question before clicking Generate Chart.")

    else:
        # Empty state placeholder
        st.markdown("""
        <div style="text-align:center; padding:3rem 1rem; color:#999;">
            <div style="font-size:3.5rem">📊</div>
            <h3 style="color:#666; margin-top:0.5rem">Ready for your question</h3>
            <p>Type a question above, pick an example from the sidebar,<br>
               or re-run a past query from <em>Recent Queries</em>.</p>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2  ·  DATA EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
with tab_explorer:
    st.subheader("Explore the Raw Dataset")
    st.caption("Browse, filter and search the full 50,000-row sales table.")

    @st.cache_data(show_spinner="Loading dataset…")
    def load_full_df() -> pd.DataFrame:
        return pd.read_csv("dataset.csv", parse_dates=["order_date"])

    full_df = load_full_df()

    # Filter controls
    with st.expander("Filters", expanded=True):
        f1, f2, f3, f4 = st.columns(4)

        with f1:
            categories = ["All"] + sorted(full_df["product_category"].unique().tolist())
            sel_cat = st.selectbox("Product Category", categories)

        with f2:
            regions = ["All"] + sorted(full_df["customer_region"].unique().tolist())
            sel_reg = st.selectbox("Customer Region", regions)

        with f3:
            methods = ["All"] + sorted(full_df["payment_method"].unique().tolist())
            sel_pay = st.selectbox("Payment Method", methods)

        with f4:
            min_rev = float(full_df["total_revenue"].min())
            max_rev = float(full_df["total_revenue"].max())
            rev_range = st.slider(
                "Total Revenue Range",
                min_value = round(min_rev),
                max_value = round(max_rev),
                value     = (round(min_rev), round(max_rev)),
                step      = 50,
            )

    # Apply filters
    filtered = full_df.copy()
    if sel_cat != "All":
        filtered = filtered[filtered["product_category"] == sel_cat]
    if sel_reg != "All":
        filtered = filtered[filtered["customer_region"] == sel_reg]
    if sel_pay != "All":
        filtered = filtered[filtered["payment_method"] == sel_pay]
    filtered = filtered[
        (filtered["total_revenue"] >= rev_range[0]) &
        (filtered["total_revenue"] <= rev_range[1])
    ]

    # Text search
    search = st.text_input(
        "Search across all text columns",
        placeholder = "e.g.  Books,  Asia,  UPI …"
    )
    if search.strip():
        mask = filtered.astype(str).apply(
            lambda col: col.str.contains(search.strip(), case=False, na=False)
        ).any(axis=1)
        filtered = filtered[mask]

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rows shown",   f"{len(filtered):,}")
    m2.metric("Total Revenue", f"${filtered['total_revenue'].sum():,.0f}")
    m3.metric("Avg Rating",
              f"{filtered['rating'].mean():.2f}" if len(filtered) else "—")
    m4.metric("Avg Discount",
              f"{filtered['discount_percent'].mean():.1f}%" if len(filtered) else "—")

    st.divider()

    # Column picker
    all_cols     = list(full_df.columns)
    default_cols = [
        "order_id", "order_date", "product_category",
        "customer_region", "quantity_sold", "total_revenue", "rating"
    ]
    sel_cols = st.multiselect("Columns to display", all_cols, default=default_cols)
    show_cols = sel_cols if sel_cols else all_cols

    # Table
    st.dataframe(
        filtered[show_cols].reset_index(drop=True),
        use_container_width = True,
        hide_index          = True,
        height              = 450,
    )

    # Download filtered CSV
    csv_bytes = filtered[show_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        label     = "⬇️ Download Filtered CSV",
        data      = csv_bytes,
        file_name = "filtered_data.csv",
        mime      = "text/csv",
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3  ·  ABOUT
# ══════════════════════════════════════════════════════════════════════════════
with tab_about:
    st.subheader("About this app")

    col_l, col_r = st.columns([3, 2])

    with col_l:
        st.markdown("""
### How it works

1. **You** type a business question in plain English.
2. **Groq** (`llama3-70b-8192`) converts it to a structured JSON containing an
   SQL query, chart type, and axis names.
3. **Python** executes the SQL safely on a local SQLite database
   loaded from `dataset.csv`.
4. **Plotly** renders an interactive chart (bar / line / pie).
5. **Groq** generates a 3-5 sentence business insight from the result.
6. Everything is displayed in **Streamlit** with KPI cards, export buttons,
   and a session-scoped query history.

---

### Workflow

```
User question
      │
      ▼
  Groq LLM  ──►  JSON { sql, chart_type, x, y }
                   │
                   ▼
           SQLite execution
                   │
                   ▼
           pandas DataFrame
                   │
           ┌───────┴────────┐
           ▼                ▼
      Plotly chart     Groq Insight
           │                │
           └───────┬────────┘
                   ▼
        KPIs · Chart · Insight · Exports
```

---

### Project files

| File | Role |
|---|---|
| `app.py` | Streamlit UI & orchestration |
| `llm.py` | Groq API call + JSON parsing |
| `database.py` | SQLite init + safe query execution |
| `chart_generator.py` | Plotly bar / line / pie builder |
| `insights.py` | AI plain-English insight generator |
| `history.py` | Session query history manager |
| `exports.py` | CSV / PNG / JSON download buttons |
        """)

    with col_r:
        st.markdown("""
### Tech stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| LLM | Groq · llama3-70b-8192 |
| Data | pandas |
| Database | SQLite (stdlib) |
| Charts | Plotly Express |

---

### Dataset schema

| Column | Type |
|---|---|
| `order_id` | INTEGER |
| `order_date` | TEXT |
| `product_category` | TEXT |
| `price` | REAL |
| `discount_percent` | REAL |
| `quantity_sold` | INTEGER |
| `customer_region` | TEXT |
| `payment_method` | TEXT |
| `rating` | REAL |
| `review_count` | INTEGER |
| `discounted_price` | REAL |
| `total_revenue` | REAL |

---

### Example questions

- Total revenue by product category
- Monthly revenue trend for 2023
- Revenue share by payment method
- Average rating per category
- Top 5 categories by quantity sold
        """)
