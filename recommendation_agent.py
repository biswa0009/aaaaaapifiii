"""
recommendation_agent.py
-----------------------
Generates prioritised, actionable business recommendations from an
AnalyticsReport produced by analytics_agent.py.

No Streamlit, no SQL, no file I/O — pure Python so it can be unit-tested
independently and called from any context.

Public API:
  generate_recommendations(report)                    → list[Recommendation]
  enrich_recommendations_with_llm(recs, df, api_key)  → list[Recommendation]
  recommendations_to_df(recs)                         → pd.DataFrame
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

from analytics_agent import AnalyticsReport


# ── Recommendation dataclass ──────────────────────────────────────────────────

@dataclass
class Recommendation:
    """A single actionable recommendation."""
    priority:    str   = "medium"   # "high" | "medium" | "low"
    category:    str   = ""         # e.g. "Growth", "Product", "Region", "Risk"
    finding:     str   = ""         # what was observed (short, factual)
    action:      str   = ""         # what to do about it
    impact:      str   = ""         # expected outcome / benefit
    detail:      str   = ""         # optional LLM-generated narrative
    confidence:  float = 1.0        # 0–1 (currently always 1.0 for rule-based)

    @property
    def priority_emoji(self) -> str:
        return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(self.priority, "⚪")

    @property
    def category_emoji(self) -> str:
        return {
            "Growth":   "📈",
            "Product":  "📦",
            "Region":   "🌍",
            "Revenue":  "💰",
            "Risk":     "⚠️",
            "Correlation": "🔗",
        }.get(self.category, "💡")


# ── Main generator ────────────────────────────────────────────────────────────

def generate_recommendations(report: AnalyticsReport) -> list[Recommendation]:
    """
    Apply a rule-based engine to the AnalyticsReport and return a
    prioritised list of Recommendation objects.

    Rules are independent; multiple rules can fire for the same report.
    """
    recs: list[Recommendation] = []

    recs.extend(_trend_rules(report))
    recs.extend(_product_rules(report))
    recs.extend(_region_rules(report))
    recs.extend(_revenue_rules(report))
    recs.extend(_growth_rules(report))
    recs.extend(_outlier_rules(report))
    recs.extend(_correlation_rules(report))

    # Sort: high → medium → low, then by category
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: (priority_order.get(r.priority, 3), r.category))

    return recs


# ── Optional LLM enrichment ───────────────────────────────────────────────────

def enrich_recommendations_with_llm(
    recs:    list[Recommendation],
    df:      pd.DataFrame,
    api_key: str = "",
) -> list[Recommendation]:
    """
    For each HIGH-priority recommendation, ask the Groq LLM to write a
    one-paragraph narrative expanding on the finding and action.

    Low/medium recs are left unchanged to keep API usage minimal.
    Falls back gracefully (returns original recs) on any error.
    """
    if not recs:
        return recs

    try:
        import os
        if api_key:
            os.environ["GROQ_API_KEY"] = api_key
        from llm import get_groq_client
        client = get_groq_client()
    except Exception:
        return recs

    system_msg = (
        "You are a business strategy consultant. Expand the following "
        "business recommendation into a compelling 2-3 sentence narrative. "
        "Be specific, actionable, and professional. Plain prose only."
    )

    for rec in recs:
        if rec.priority != "high":
            continue
        user_msg = (
            f"Finding: {rec.finding}\n"
            f"Recommended Action: {rec.action}\n"
            f"Expected Impact: {rec.impact}"
        )
        try:
            response = client.chat.completions.create(
                model       = "llama-3.3-70b-versatile",
                messages    = [
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_msg},
                ],
                temperature = 0.4,
                max_tokens  = 200,
            )
            rec.detail = response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[RecommendationAgent] LLM enrich skipped for '{rec.category}': {exc}")

    return recs


# ── DataFrame helper ──────────────────────────────────────────────────────────

def recommendations_to_df(recs: list[Recommendation]) -> pd.DataFrame:
    """Convert recommendation list to a pandas DataFrame for export or display."""
    if not recs:
        return pd.DataFrame(columns=["Priority", "Category", "Finding", "Action", "Impact"])
    return pd.DataFrame([
        {
            "Priority": rec.priority.title(),
            "Category": rec.category,
            "Finding":  rec.finding,
            "Action":   rec.action,
            "Impact":   rec.impact,
        }
        for rec in recs
    ])


# ── Rule functions ────────────────────────────────────────────────────────────

def _trend_rules(report: AnalyticsReport) -> list[Recommendation]:
    recs = []
    t = report.trend
    if not t:
        return recs

    trend_dir = t.get("overall_trend", "flat")
    avg_growth = t.get("avg_monthly_growth_pct", 0.0)

    if trend_dir == "downward":
        recs.append(Recommendation(
            priority = "high",
            category = "Growth",
            finding  = f"Overall revenue trend is downward with avg monthly growth of {avg_growth:.1f}%.",
            action   = "Conduct root-cause analysis on the declining months; investigate product mix, pricing changes, and regional demand shifts.",
            impact   = "Reversing the downward trend could recover lost revenue and restore growth momentum.",
        ))
    elif trend_dir == "upward" and avg_growth > 5:
        recs.append(Recommendation(
            priority = "low",
            category = "Growth",
            finding  = f"Revenue is growing strongly with avg monthly growth of {avg_growth:.1f}%.",
            action   = "Document and scale the marketing and operational practices driving this growth.",
            impact   = "Sustaining the growth rate will compound revenue significantly over the next year.",
        ))
    elif trend_dir == "flat":
        recs.append(Recommendation(
            priority = "medium",
            category = "Growth",
            finding  = "Revenue trend is flat — growth has plateaued.",
            action   = "Explore new customer segments, geographic expansion, or product line extensions to reignite growth.",
            impact   = "Breaking the plateau with even 3–5% monthly growth significantly improves annual revenue.",
        ))

    # Peak & trough insights
    peak = t.get("peak_period")
    trough = t.get("trough_period")
    if peak and trough and peak != trough:
        recs.append(Recommendation(
            priority = "medium",
            category = "Growth",
            finding  = f"Revenue peaked in {peak} and hit its lowest in {trough}.",
            action   = f"Analyse what drove success in {peak} (promotions, seasonality, launches) and replicate those conditions. Address the {trough} dip with targeted campaigns.",
            impact   = "Smoothing seasonal volatility improves cash flow predictability and inventory planning.",
        ))

    return recs


def _product_rules(report: AnalyticsReport) -> list[Recommendation]:
    recs = []
    bwp = report.best_worst_products
    if not bwp:
        return recs

    best  = bwp.get("best", [])
    worst = bwp.get("worst", [])

    if best:
        top = best[0]
        recs.append(Recommendation(
            priority = "low",
            category = "Product",
            finding  = f"'{top['label']}' is the top-performing product/category with ${top['value']:,.0f} in revenue.",
            action   = f"Expand SKU range, increase stock levels, and feature '{top['label']}' prominently in marketing campaigns.",
            impact   = "Amplifying top performers typically yields a 10–20% revenue lift in that category.",
        ))

    if len(worst) >= 1:
        bottom = worst[0]
        recs.append(Recommendation(
            priority = "medium" if bottom["value"] < (best[0]["value"] * 0.1 if best else 1) else "low",
            category = "Product",
            finding  = f"'{bottom['label']}' is the lowest-performing product/category with only ${bottom['value']:,.0f} in revenue.",
            action   = f"Review pricing, promotion, and shelf placement for '{bottom['label']}'. Consider discounting, bundling, or discontinuation if margins are thin.",
            impact   = "Improving or pruning underperformers reduces operational overhead and focuses resources on winners.",
        ))

    return recs


def _region_rules(report: AnalyticsReport) -> list[Recommendation]:
    recs = []
    bwr = report.best_worst_regions
    if not bwr:
        return recs

    best  = bwr.get("best", [])
    worst = bwr.get("worst", [])

    if best and worst:
        top    = best[0]
        bottom = worst[0]
        gap_pct = 0.0
        if top["value"] > 0:
            gap_pct = (top["value"] - bottom["value"]) / top["value"] * 100

        if gap_pct > 40:
            recs.append(Recommendation(
                priority = "high",
                category = "Region",
                finding  = (
                    f"Large regional revenue gap: '{top['label']}' leads with "
                    f"${top['value']:,.0f} while '{bottom['label']}' lags at "
                    f"${bottom['value']:,.0f} ({gap_pct:.0f}% gap)."
                ),
                action   = (
                    f"Increase marketing budget in '{bottom['label']}': localise campaigns, "
                    f"partner with local distributors, and investigate if pricing is a barrier."
                ),
                impact   = f"Closing even half the gap in '{bottom['label']}' could unlock significant incremental revenue.",
            ))
        else:
            recs.append(Recommendation(
                priority = "low",
                category = "Region",
                finding  = f"'{top['label']}' is the top region; regional performance is relatively balanced.",
                action   = f"Continue investing in '{top['label']}' while running targeted pilots in lower-performing regions.",
                impact   = "Balanced regional growth reduces concentration risk.",
            ))

    return recs


def _revenue_rules(report: AnalyticsReport) -> list[Recommendation]:
    recs = []
    rp = report.revenue_profit
    if not rp:
        return recs

    total = rp.get("total_revenue")
    avg   = rp.get("avg_revenue")
    std   = rp.get("revenue_std")

    if total and avg and std:
        cv = std / avg if avg > 0 else 0  # Coefficient of variation
        if cv > 0.8:
            recs.append(Recommendation(
                priority = "medium",
                category = "Revenue",
                finding  = f"Revenue per transaction is highly variable (CV={cv:.2f}), indicating inconsistent deal sizes.",
                action   = "Implement value-based pricing tiers and upsell/cross-sell programmes to normalise deal sizes.",
                impact   = "Reducing revenue volatility improves forecast accuracy and operational planning.",
            ))

    margin = rp.get("avg_margin_pct")
    if margin is not None:
        if margin < 15:
            recs.append(Recommendation(
                priority = "high",
                category = "Revenue",
                finding  = f"Average profit margin is low at {margin:.1f}%.",
                action   = "Audit cost structures, renegotiate supplier contracts, and identify low-margin SKUs for repricing or removal.",
                impact   = "Each 1% margin improvement directly increases net profit.",
            ))
        elif margin > 40:
            recs.append(Recommendation(
                priority = "low",
                category = "Revenue",
                finding  = f"Profit margin is strong at {margin:.1f}%.",
                action   = "Reinvest margins into customer acquisition and R&D to sustain competitive advantage.",
                impact   = "High margins provide a strategic buffer for growth investments.",
            ))

    return recs


def _growth_rules(report: AnalyticsReport) -> list[Recommendation]:
    recs = []
    g = report.growth
    if not g:
        return recs

    cagr = g.get("cagr_pct")
    wm   = g.get("worst_mom_growth")
    bm   = g.get("best_mom_growth")

    if cagr is not None and cagr < 0:
        recs.append(Recommendation(
            priority = "high",
            category = "Growth",
            finding  = f"CAGR is negative at {cagr:.1f}% — the business is shrinking year-over-year.",
            action   = "Immediately review product-market fit, customer churn, and competitive positioning. Prioritise retention over acquisition.",
            impact   = "Stabilising at 0% growth stops the bleeding; a 5% positive CAGR restores investor confidence.",
        ))
    elif cagr is not None and cagr > 20:
        recs.append(Recommendation(
            priority = "low",
            category = "Growth",
            finding  = f"Impressive CAGR of {cagr:.1f}% — strong compound growth.",
            action   = "Ensure supply chain and team capacity can scale with demand to avoid fulfilment bottlenecks.",
            impact   = "Proactive scaling prevents growth from becoming a service quality liability.",
        ))

    if wm and wm["growth_pct"] < -20:
        recs.append(Recommendation(
            priority = "medium",
            category = "Growth",
            finding  = f"Severe revenue decline in {wm['period']}: {wm['growth_pct']:.1f}% MoM.",
            action   = f"Investigate the root cause of the {wm['period']} decline — external events, stockouts, campaign lapses, or competitive pressure.",
            impact   = "Understanding the cause prevents recurrence and informs crisis response playbooks.",
        ))

    if bm and bm["growth_pct"] > 30:
        recs.append(Recommendation(
            priority = "low",
            category = "Growth",
            finding  = f"Exceptional growth spike in {bm['period']}: +{bm['growth_pct']:.1f}% MoM.",
            action   = f"Document what drove the {bm['period']} spike (promotion, product launch, viral moment) and create a repeatable playbook.",
            impact   = "A repeatable growth spike playbook can be deployed in slow periods to artificially stimulate demand.",
        ))

    return recs


def _outlier_rules(report: AnalyticsReport) -> list[Recommendation]:
    recs = []
    outliers = report.outliers
    if not outliers:
        return recs

    for col, info in outliers.items():
        n = info.get("n_outliers", 0)
        pct = info.get("outlier_pct", 0.0)
        if pct > 5:
            recs.append(Recommendation(
                priority = "medium",
                category = "Risk",
                finding  = f"Column '{col}' has {n} outliers ({pct:.1f}% of rows) outside the normal range [{info['lower_bound']:,.2f} – {info['upper_bound']:,.2f}].",
                action   = f"Investigate outlier transactions in '{col}' — they may indicate data entry errors, fraud, exceptional deals, or process anomalies.",
                impact   = "Addressing data quality outliers improves model accuracy and reduces operational risk.",
            ))

    return recs


def _correlation_rules(report: AnalyticsReport) -> list[Recommendation]:
    recs = []
    corr = report.correlation
    if not corr:
        return recs

    strong = corr.get("strong_pairs", [])
    for pair in strong[:2]:   # top 2 strongest pairs only
        ca, cb, r = pair["col_a"], pair["col_b"], pair["r"]
        direction  = pair["direction"]
        strength   = pair["strength"]

        if direction == "positive":
            recs.append(Recommendation(
                priority = "low",
                category = "Correlation",
                finding  = f"'{ca}' and '{cb}' have a {strength} positive correlation (r={r:.2f}).",
                action   = f"Leverage this relationship: increasing '{ca}' likely drives '{cb}'. Consider bundling or pricing strategies that optimise both.",
                impact   = "Acting on positive correlations allows efficient resource allocation with compounding returns.",
            ))
        else:
            recs.append(Recommendation(
                priority = "medium",
                category = "Correlation",
                finding  = f"'{ca}' and '{cb}' have a {strength} negative correlation (r={r:.2f}).",
                action   = f"Investigate the trade-off between '{ca}' and '{cb}'. A structural change (e.g. discount strategy) may be needed to decouple them.",
                impact   = "Understanding negative correlations prevents inadvertently hurting one metric while optimising another.",
            ))

    return recs
