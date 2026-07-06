"""
database.py
-----------
Handles all SQLite operations:
  - Loading dataset.csv into an in-memory / file-based SQLite database
  - Executing SQL queries safely and returning DataFrames
"""

import sqlite3
import pandas as pd
import os
import re

# ── Constants ────────────────────────────────────────────────────────────────
DB_PATH     = "sales.db"       # Persistent SQLite file (created on first run)
TABLE_NAME  = "sales"
CSV_PATH    = "dataset.csv"

# Columns present in the CSV – used for hallucination detection
VALID_COLUMNS = {
    "order_id", "order_date", "product_id", "product_category",
    "price", "discount_percent", "quantity_sold", "customer_region",
    "payment_method", "rating", "review_count", "discounted_price",
    "total_revenue"
}


# ── Database initialisation ───────────────────────────────────────────────────
def init_db() -> sqlite3.Connection:
    """
    Create (or open) the SQLite database and load dataset.csv into it.
    Re-creates the table every time so the DB always reflects the CSV.
    Returns an open connection.
    """
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(
            f"'{CSV_PATH}' not found. Place it in the same folder as app.py."
        )

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)

    # Load CSV → DataFrame → SQLite table (replace so it's always fresh)
    df = pd.read_csv(CSV_PATH, parse_dates=["order_date"])
    df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)

    conn.commit()
    print(f"[DB] Loaded {len(df):,} rows into '{TABLE_NAME}' table.")
    return conn


# ── Query validation ──────────────────────────────────────────────────────────
def _check_columns(sql: str) -> list[str]:
    """
    Scan the SQL string for column names not in VALID_COLUMNS.
    Returns a list of suspicious names (empty = all fine).
    """
    # Tokenise the SQL into bare words (remove punctuation / keywords)
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", sql.lower())

    sql_keywords = {
        "select", "from", "where", "group", "by", "order", "limit",
        "having", "join", "on", "as", "and", "or", "not", "in",
        "sum", "avg", "count", "min", "max", "distinct", "desc",
        "asc", "between", "like", "is", "null", "case", "when",
        "then", "else", "end", "strftime", "date", "cast", "round",
        table_name_lower := TABLE_NAME.lower(),
    }

    suspicious = [
        t for t in tokens
        if t not in sql_keywords
        and t not in VALID_COLUMNS
        and not t.isdigit()
    ]
    return suspicious


# ── Safe query executor ───────────────────────────────────────────────────────
def run_query(conn: sqlite3.Connection, sql: str) -> tuple[pd.DataFrame | None, str | None]:
    """
    Execute *sql* on *conn* and return (DataFrame, None) on success
    or (None, error_message) on failure.

    Safety checks applied:
      1. Only SELECT statements allowed
      2. Column hallucination detection
      3. Empty-result detection
    """
    sql = sql.strip().rstrip(";")

    # 1 · Reject non-SELECT statements
    if not sql.upper().startswith("SELECT"):
        return None, "Only SELECT queries are permitted."

    # 2 · Light hallucination check
    bad_cols = _check_columns(sql)
    if bad_cols:
        # Don't hard-block – sometimes they're aliases or sub-expressions.
        # Just log; the actual SQL execution will raise if truly invalid.
        print(f"[DB] Warning – unrecognised tokens in SQL: {bad_cols}")

    # 3 · Execute
    try:
        df = pd.read_sql_query(sql, conn)
    except Exception as exc:
        return None, f"SQL execution error: {exc}"

    # 4 · Empty result
    if df.empty:
        return None, "The query returned no results for the current dataset."

    return df, None


# ── Schema helper (used in LLM prompt) ───────────────────────────────────────
def get_schema_description() -> str:
    """Return a human-readable schema string for use in the LLM prompt."""
    return f"""
Table name : {TABLE_NAME}
Columns    :
  order_id          INTEGER   – unique order identifier
  order_date        TEXT      – sale date  (format: YYYY-MM-DD)
  product_id        INTEGER   – product identifier
  product_category  TEXT      – category  (Books, Fashion, Sports, Beauty,
                                            Electronics, Home & Kitchen)
  price             REAL      – original unit price (USD)
  discount_percent  REAL      – discount applied  (0–30)
  quantity_sold     INTEGER   – units sold per order
  customer_region   TEXT      – region  (North America, Asia, Europe,
                                         Middle East)
  payment_method    TEXT      – (UPI, Credit Card, Debit Card, Wallet,
                                  Cash on Delivery)
  rating            REAL      – customer rating  (1.0–5.0)
  review_count      INTEGER   – number of reviews
  discounted_price  REAL      – price after discount
  total_revenue     REAL      – discounted_price × quantity_sold
""".strip()
