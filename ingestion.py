"""
ingestion.py
------------
Improved data ingestion pipeline supporting CSV and Excel (.xlsx).

Features:
  - Reads CSV (pd.read_csv) and Excel/XLSX (pd.read_excel via openpyxl)
  - Auto-detects numeric, categorical, and datetime columns
  - Handles missing values (fills or drops, with configurable strategy)
  - Detects and drops duplicate rows
  - Generates a rich dataset summary report

Public API:
  ingest_file(uploaded_file_or_path)  → (df, summary)
  detect_column_types(df)             → {"numeric": [...], "categorical": [...], "datetime": [...]}
  handle_missing_and_duplicates(df)   → (cleaned_df, report_dict)
  generate_dataset_summary(df)        → dict
"""

from __future__ import annotations

import io
import warnings
from pathlib import Path
from typing import BinaryIO, Union

import pandas as pd
import numpy as np

# ── Column type detection ─────────────────────────────────────────────────────

def detect_column_types(df: pd.DataFrame) -> dict[str, list[str]]:
    """
    Classify every column in *df* into one of three buckets:
      - numeric    : int or float columns (including those stored as object
                     but parseable as numbers)
      - categorical: string / low-cardinality object columns
      - datetime   : already datetime dtype, or columns parseable as dates

    Returns
    -------
    dict with keys "numeric", "categorical", "datetime", each holding a list
    of column names.
    """
    numeric:     list[str] = []
    categorical: list[str] = []
    datetime_cols: list[str] = []

    for col in df.columns:
        dtype = df[col].dtype

        # Already a datetime
        if pd.api.types.is_datetime64_any_dtype(dtype):
            datetime_cols.append(col)
            continue

        # Already numeric
        if pd.api.types.is_numeric_dtype(dtype):
            numeric.append(col)
            continue

        # Object column — try to infer
        sample = df[col].dropna().head(500)
        if sample.empty:
            categorical.append(col)
            continue

        # Try numeric coercion
        coerced_numeric = pd.to_numeric(sample, errors="coerce")
        if coerced_numeric.notna().mean() >= 0.85:
            numeric.append(col)
            continue

        # Try datetime parsing (suppress warnings for unparseable columns)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                coerced_dt = pd.to_datetime(sample, infer_datetime_format=True, errors="coerce")
                if coerced_dt.notna().mean() >= 0.80:
                    datetime_cols.append(col)
                    continue
            except Exception:
                pass

        # Default → categorical
        categorical.append(col)

    return {
        "numeric":     numeric,
        "categorical": categorical,
        "datetime":    datetime_cols,
    }


# ── Missing value & duplicate handler ────────────────────────────────────────

def handle_missing_and_duplicates(
    df: pd.DataFrame,
    numeric_fill_strategy: str = "median",   # "median" | "mean" | "zero" | "drop"
    categorical_fill_value: str = "Unknown",
    drop_duplicate_rows: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """
    Clean *df* by handling missing values and duplicates.

    Parameters
    ----------
    df                      : input DataFrame
    numeric_fill_strategy   : how to fill numeric NaN values
    categorical_fill_value  : string to fill categorical NaN values
    drop_duplicate_rows     : whether to drop fully-duplicate rows

    Returns
    -------
    (cleaned_df, report_dict)
    report_dict keys:
      rows_before, rows_after, duplicates_dropped, missing_per_column,
      numeric_filled, categorical_filled, total_missing_filled
    """
    df = df.copy()
    rows_before   = len(df)
    missing_before = df.isnull().sum().to_dict()

    col_types = detect_column_types(df)

    # ── 1. Drop fully duplicate rows ─────────────────────────────────────────
    duplicates_dropped = 0
    if drop_duplicate_rows:
        n_before = len(df)
        df = df.drop_duplicates()
        duplicates_dropped = n_before - len(df)

    # ── 2. Fill numeric columns ───────────────────────────────────────────────
    numeric_filled = 0
    for col in col_types["numeric"]:
        if col not in df.columns:
            continue
        # Coerce object-typed-but-numeric columns
        df[col] = pd.to_numeric(df[col], errors="coerce")
        n_missing = df[col].isnull().sum()
        if n_missing == 0:
            continue

        if numeric_fill_strategy == "median":
            fill_val = df[col].median()
        elif numeric_fill_strategy == "mean":
            fill_val = df[col].mean()
        elif numeric_fill_strategy == "zero":
            fill_val = 0.0
        elif numeric_fill_strategy == "drop":
            df = df.dropna(subset=[col])
            numeric_filled += n_missing
            continue
        else:
            fill_val = df[col].median()

        df[col] = df[col].fillna(fill_val)
        numeric_filled += n_missing

    # ── 3. Fill categorical / datetime columns ────────────────────────────────
    categorical_filled = 0
    for col in col_types["categorical"] + col_types["datetime"]:
        if col not in df.columns:
            continue
        n_missing = df[col].isnull().sum()
        if n_missing > 0:
            df[col] = df[col].fillna(categorical_fill_value)
            categorical_filled += n_missing

    rows_after = len(df)

    report = {
        "rows_before":         rows_before,
        "rows_after":          rows_after,
        "duplicates_dropped":  duplicates_dropped,
        "missing_per_column":  missing_before,
        "numeric_filled":      numeric_filled,
        "categorical_filled":  categorical_filled,
        "total_missing_filled": numeric_filled + categorical_filled,
    }
    return df, report


# ── Dataset summary ───────────────────────────────────────────────────────────

def generate_dataset_summary(df: pd.DataFrame) -> dict:
    """
    Generate a rich summary of the dataset.

    Returns
    -------
    dict with keys:
      n_rows, n_cols, missing_values (total), missing_pct, duplicates,
      column_types (from detect_column_types),
      dtypes (col→dtype string),
      numeric_stats (col→{mean,std,min,max,median}),
      top_categoricals (col→{values: [...]}) for categorical cols
    """
    col_types   = detect_column_types(df)
    total_cells = df.shape[0] * df.shape[1] if df.shape[1] > 0 else 1
    missing_total = int(df.isnull().sum().sum())
    duplicates    = int(df.duplicated().sum())

    # Per-column dtypes (human-readable)
    dtypes = {col: str(df[col].dtype) for col in df.columns}

    # Numeric stats
    numeric_stats: dict[str, dict] = {}
    for col in col_types["numeric"]:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        numeric_stats[col] = {
            "mean":   round(float(series.mean()), 4),
            "std":    round(float(series.std()), 4),
            "min":    round(float(series.min()), 4),
            "max":    round(float(series.max()), 4),
            "median": round(float(series.median()), 4),
        }

    # Top categoricals (up to 10 unique values shown)
    top_categoricals: dict[str, dict] = {}
    for col in col_types["categorical"]:
        counts = df[col].value_counts().head(10)
        top_categoricals[col] = {
            "unique_count": int(df[col].nunique()),
            "top_values":   counts.index.tolist(),
            "top_counts":   counts.tolist(),
        }

    # Datetime ranges
    datetime_ranges: dict[str, dict] = {}
    for col in col_types["datetime"]:
        try:
            series = pd.to_datetime(df[col], errors="coerce").dropna()
            if not series.empty:
                datetime_ranges[col] = {
                    "min": str(series.min().date()),
                    "max": str(series.max().date()),
                    "range_days": int((series.max() - series.min()).days),
                }
        except Exception:
            pass

    return {
        "n_rows":           len(df),
        "n_cols":           len(df.columns),
        "missing_values":   missing_total,
        "missing_pct":      round(missing_total / total_cells * 100, 2),
        "duplicates":       duplicates,
        "column_types":     col_types,
        "dtypes":           dtypes,
        "numeric_stats":    numeric_stats,
        "top_categoricals": top_categoricals,
        "datetime_ranges":  datetime_ranges,
    }


# ── File ingestor ─────────────────────────────────────────────────────────────

def ingest_file(
    source: Union[str, Path, BinaryIO],
    sheet_name: Union[str, int] = 0,
    date_columns: list[str] | None = None,
    clean: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """
    Read a CSV or Excel (.xlsx) file into a DataFrame and generate a summary.

    Parameters
    ----------
    source       : file path (str/Path) or a file-like object (e.g. Streamlit UploadedFile)
    sheet_name   : sheet for Excel files (default: first sheet)
    date_columns : optional list of column names to force-parse as datetime
    clean        : if True, run handle_missing_and_duplicates automatically

    Returns
    -------
    (df, report)
    report contains:
      file_type, original_summary, cleaning_report (if clean=True)
    """
    # ── Determine file type ──────────────────────────────────────────────────
    file_type = _detect_file_type(source)

    # ── Read ─────────────────────────────────────────────────────────────────
    if file_type == "csv":
        df = _read_csv(source, date_columns)
    elif file_type in ("xlsx", "xls"):
        df = _read_excel(source, sheet_name, date_columns)
    else:
        raise ValueError(
            f"Unsupported file type: '{file_type}'. Supported: CSV, XLSX/XLS."
        )

    # ── Auto-detect and coerce datetime columns ───────────────────────────────
    df = _coerce_datetime_columns(df, date_columns)

    # ── Generate summary before cleaning ─────────────────────────────────────
    original_summary = generate_dataset_summary(df)
    original_summary["file_type"] = file_type

    report: dict = {
        "file_type":        file_type,
        "original_summary": original_summary,
        "cleaning_report":  None,
    }

    # ── Optional cleaning ─────────────────────────────────────────────────────
    if clean:
        df, cleaning_report = handle_missing_and_duplicates(df)
        report["cleaning_report"] = cleaning_report

    return df, report


# ── Internal helpers ──────────────────────────────────────────────────────────

def _detect_file_type(source) -> str:
    """Return lowercase file extension ('csv', 'xlsx', 'xls') from source."""
    if isinstance(source, (str, Path)):
        ext = Path(source).suffix.lower().lstrip(".")
        return ext or "csv"
    # File-like object — try .name attribute (Streamlit UploadedFile has it)
    name = getattr(source, "name", "") or ""
    ext  = Path(name).suffix.lower().lstrip(".")
    return ext or "csv"


def _read_csv(source, date_columns: list[str] | None) -> pd.DataFrame:
    """Read CSV, trying UTF-8 then latin-1 encoding as fallback."""
    kwargs: dict = {}
    if date_columns:
        kwargs["parse_dates"] = date_columns
    try:
        return pd.read_csv(source, encoding="utf-8", **kwargs)
    except UnicodeDecodeError:
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_csv(source, encoding="latin-1", **kwargs)


def _read_excel(source, sheet_name, date_columns: list[str] | None) -> pd.DataFrame:
    """Read Excel; requires openpyxl for .xlsx."""
    try:
        kwargs: dict = {"sheet_name": sheet_name}
        if date_columns:
            kwargs["parse_dates"] = date_columns
        return pd.read_excel(source, engine="openpyxl", **kwargs)
    except ImportError:
        raise ImportError(
            "openpyxl is required to read .xlsx files. "
            "Install it with: pip install openpyxl"
        )


def _coerce_datetime_columns(
    df: pd.DataFrame, explicit: list[str] | None
) -> pd.DataFrame:
    """
    For any column not already datetime:
      1. If it's in *explicit*, force-parse it.
      2. Otherwise, try to auto-detect if the column name contains common
         date keywords and >80% of values parse successfully.
    """
    DATE_KEYWORDS = {"date", "time", "timestamp", "created", "updated", "at"}
    df = df.copy()

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col].dtype):
            continue

        # Force-parse explicitly named columns
        if explicit and col in explicit:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df[col] = pd.to_datetime(df[col], errors="coerce",
                                         infer_datetime_format=True)
            continue

        # Auto-detect by name hint
        col_lower = col.lower()
        if any(kw in col_lower for kw in DATE_KEYWORDS):
            sample = df[col].dropna().head(200)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    coerced = pd.to_datetime(sample, errors="coerce",
                                             infer_datetime_format=True)
                    if coerced.notna().mean() >= 0.80:
                        df[col] = pd.to_datetime(df[col], errors="coerce",
                                                 infer_datetime_format=True)
                except Exception:
                    pass

    return df
