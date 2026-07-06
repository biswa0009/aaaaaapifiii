"""
forecasting.py
--------------
Time-series sales/revenue forecasting with a graceful library fallback chain:

  1. Prophet      — if installed (pip install prophet)
  2. ARIMA        — if statsmodels installed (pip install statsmodels)
  3. Linear Regression — scikit-learn (hard dependency, always available)

Public API:
  run_forecast(df, date_col, value_col, periods, freq) → ForecastResult
  detect_available_forecaster()                         → str
  prepare_time_series(df, date_col, value_col, freq)    → pd.Series
  forecast_linear(series, periods)                      → ForecastResult
  forecast_arima(series, periods)                       → ForecastResult
  forecast_prophet(series, periods)                     → ForecastResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import warnings

import numpy as np
import pandas as pd


# ── ForecastResult dataclass ──────────────────────────────────────────────────

@dataclass
class ForecastResult:
    """Unified container for forecast outputs."""
    method:        str                     = "linear"
    periods:       int                     = 6
    freq:          str                     = "ME"
    historical_df: Optional[pd.DataFrame] = None   # columns: date, value
    forecast_df:   Optional[pd.DataFrame] = None   # columns: date, predicted, lower_ci, upper_ci
    metrics:       dict                    = field(default_factory=dict)
    error:         str                     = ""     # non-empty if forecasting failed


# ── Library detector ──────────────────────────────────────────────────────────

def detect_available_forecaster() -> str:
    """
    Return the best available forecasting library:
      "prophet" > "arima" > "linear"
    """
    try:
        import prophet  # noqa: F401
        return "prophet"
    except ImportError:
        pass
    try:
        import statsmodels  # noqa: F401
        return "arima"
    except ImportError:
        pass
    return "linear"


# ── Time-series preparation ───────────────────────────────────────────────────

def prepare_time_series(
    df:        pd.DataFrame,
    date_col:  str,
    value_col: str,
    freq:      str = "ME",
) -> pd.Series:
    """
    Aggregate *df* by calendar period and return a clean pd.Series with a
    DatetimeIndex, sorted ascending, with zeros replaced by NaN then
    forward-filled to handle gaps.

    Raises ValueError if fewer than 4 periods are available.
    """
    df = df.copy()
    df[date_col]  = pd.to_datetime(df[date_col], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=[date_col, value_col])

    if df.empty:
        raise ValueError("No valid date/value pairs found in the data.")

    df = df.set_index(date_col).sort_index()
    try:
        series = df[value_col].resample(freq).sum()
    except Exception:
        series = df[value_col].resample("MS").sum()

    series = series[series > 0]
    series = series.asfreq(freq, fill_value=np.nan)

    # Forward-fill up to 2 periods for small gaps; drop the rest
    series = series.fillna(method="ffill", limit=2).dropna()

    if len(series) < 4:
        raise ValueError(
            f"Need at least 4 historical periods to forecast; got {len(series)}."
        )
    return series


# ── Linear Regression forecast ────────────────────────────────────────────────

def forecast_linear(
    series:  pd.Series,
    periods: int = 6,
) -> ForecastResult:
    """
    Simple linear regression on a numeric time index.
    Confidence intervals are ±1.96 * residual std (approximate 95% CI).
    """
    from sklearn.linear_model import LinearRegression

    n    = len(series)
    X    = np.arange(n).reshape(-1, 1)
    y    = series.values.astype(float)

    model = LinearRegression()
    model.fit(X, y)

    y_pred     = model.predict(X)
    residuals  = y - y_pred
    resid_std  = float(np.std(residuals))
    r_squared  = float(model.score(X, y))

    # Generate future dates
    last_date  = series.index[-1]
    future_idx = pd.date_range(start=last_date, periods=periods + 1, freq=series.index.freq or "ME")[1:]
    X_future   = np.arange(n, n + periods).reshape(-1, 1)
    y_future   = model.predict(X_future)

    margin = 1.96 * resid_std

    forecast_df = pd.DataFrame({
        "date":      future_idx,
        "predicted": np.maximum(y_future, 0).round(2),
        "lower_ci":  np.maximum(y_future - margin, 0).round(2),
        "upper_ci":  (y_future + margin).round(2),
    })

    historical_df = pd.DataFrame({
        "date":  series.index,
        "value": series.values.round(2),
    })

    # MAPE on in-sample
    mape = _mape(y, y_pred)

    return ForecastResult(
        method        = "linear",
        periods       = periods,
        historical_df = historical_df,
        forecast_df   = forecast_df,
        metrics       = {
            "r_squared": round(r_squared, 4),
            "mape":      round(mape, 2) if mape is not None else None,
            "resid_std": round(resid_std, 2),
        },
    )


# ── ARIMA forecast ────────────────────────────────────────────────────────────

def forecast_arima(
    series:  pd.Series,
    periods: int = 6,
    order:   tuple = (1, 1, 1),
) -> ForecastResult:
    """
    ARIMA forecast using statsmodels.

    Falls back to LinearRegression if statsmodels is not installed.
    """
    try:
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError:
        print("[Forecast] statsmodels not available — falling back to LinearRegression.")
        result = forecast_linear(series, periods)
        result.method = "arima→linear (fallback)"
        return result

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            model  = ARIMA(series, order=order)
            fitted = model.fit()
            pred   = fitted.get_forecast(steps=periods)
            pred_mean = pred.predicted_mean
            conf_int  = pred.conf_int(alpha=0.05)

            last_date  = series.index[-1]
            future_idx = pd.date_range(
                start=last_date, periods=periods + 1,
                freq=series.index.freq or "ME"
            )[1:]

            forecast_df = pd.DataFrame({
                "date":      future_idx,
                "predicted": np.maximum(pred_mean.values, 0).round(2),
                "lower_ci":  np.maximum(conf_int.iloc[:, 0].values, 0).round(2),
                "upper_ci":  conf_int.iloc[:, 1].values.round(2),
            })

            historical_df = pd.DataFrame({
                "date":  series.index,
                "value": series.values.round(2),
            })

            in_sample = fitted.predict(start=0, end=len(series) - 1)
            mape = _mape(series.values, in_sample)
            aic  = round(float(fitted.aic), 2)

            return ForecastResult(
                method        = "arima",
                periods       = periods,
                historical_df = historical_df,
                forecast_df   = forecast_df,
                metrics       = {
                    "aic":  aic,
                    "mape": round(mape, 2) if mape is not None else None,
                    "order": str(order),
                },
            )
        except Exception as exc:
            print(f"[Forecast] ARIMA failed ({exc}) — falling back to LinearRegression.")
            result = forecast_linear(series, periods)
            result.method = f"arima→linear (fallback: {exc})"
            return result


# ── Prophet forecast ──────────────────────────────────────────────────────────

def forecast_prophet(
    series:  pd.Series,
    periods: int = 6,
) -> ForecastResult:
    """
    Prophet forecast.

    Falls back through ARIMA → LinearRegression if Prophet is not installed
    or fails.
    """
    try:
        from prophet import Prophet
    except ImportError:
        print("[Forecast] prophet not available — trying ARIMA.")
        return forecast_arima(series, periods)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            df_prophet = pd.DataFrame({
                "ds": series.index.to_timestamp() if hasattr(series.index, "to_timestamp")
                      else series.index,
                "y":  series.values.astype(float),
            })

            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                interval_width=0.95,
                seasonality_mode="multiplicative",
            )
            model.fit(df_prophet)

            future = model.make_future_dataframe(periods=periods, freq="ME")
            forecast = model.predict(future)

            hist_len = len(series)
            hist_part = forecast.iloc[:hist_len]
            fut_part  = forecast.iloc[hist_len:]

            historical_df = pd.DataFrame({
                "date":  df_prophet["ds"],
                "value": df_prophet["y"].round(2),
            })

            forecast_df = pd.DataFrame({
                "date":      fut_part["ds"].values,
                "predicted": np.maximum(fut_part["yhat"].values, 0).round(2),
                "lower_ci":  np.maximum(fut_part["yhat_lower"].values, 0).round(2),
                "upper_ci":  fut_part["yhat_upper"].values.round(2),
            })

            # MAPE on historical portion
            mape = _mape(df_prophet["y"].values, hist_part["yhat"].values)

            return ForecastResult(
                method        = "prophet",
                periods       = periods,
                historical_df = historical_df,
                forecast_df   = forecast_df,
                metrics       = {
                    "mape":              round(mape, 2) if mape is not None else None,
                    "seasonality_mode":  "multiplicative",
                    "interval_width":    0.95,
                },
            )
        except Exception as exc:
            print(f"[Forecast] Prophet failed ({exc}) — falling back to ARIMA.")
            return forecast_arima(series, periods)


# ── Unified entry point ───────────────────────────────────────────────────────

def run_forecast(
    df:        pd.DataFrame,
    date_col:  str,
    value_col: str,
    periods:   int = 6,
    freq:      str = "ME",
    method:    str = "auto",   # "auto" | "linear" | "arima" | "prophet"
) -> ForecastResult:
    """
    End-to-end forecasting pipeline.

    Parameters
    ----------
    df        : source DataFrame
    date_col  : date column name
    value_col : metric column to forecast
    periods   : number of future periods to predict
    freq      : pandas offset alias for aggregation (default: ME = month-end)
    method    : "auto" uses detect_available_forecaster() to pick the best

    Returns
    -------
    ForecastResult (never raises — errors are captured in ForecastResult.error)
    """
    try:
        series = prepare_time_series(df, date_col, value_col, freq)
    except ValueError as exc:
        return ForecastResult(error=str(exc))

    chosen = method if method != "auto" else detect_available_forecaster()

    try:
        if chosen == "prophet":
            result = forecast_prophet(series, periods)
        elif chosen == "arima":
            result = forecast_arima(series, periods)
        else:
            result = forecast_linear(series, periods)
    except Exception as exc:
        # Last-resort fallback
        try:
            result = forecast_linear(series, periods)
            result.method = f"linear (emergency fallback from {chosen}: {exc})"
        except Exception as exc2:
            return ForecastResult(error=f"All forecasters failed: {exc2}")

    result.freq = freq
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _mape(actual: np.ndarray, predicted: np.ndarray) -> Optional[float]:
    """
    Mean Absolute Percentage Error.
    Returns None if any actual value is 0 (to avoid division by zero).
    """
    actual    = np.array(actual, dtype=float)
    predicted = np.array(predicted, dtype=float)
    mask      = actual != 0
    if mask.sum() == 0:
        return None
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)
