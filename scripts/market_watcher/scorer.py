"""Impact scoring engine — classifies events into 4 severity levels."""

from typing import Any

LEVELS = ("critical", "high", "medium", "low")


def score_fred_release(obs: dict, config: dict) -> str:
    """Score a FRED data release by importance and surprise factor."""
    series_id = obs.get("series_id", "").upper()
    critical_series = {"CPIAUCSL", "PAYEMS", "GDP", "GDPC1", "PCEPI", "UNRATE", "FEDFUNDS"}
    high_series = {"ICSA", "RSAFS", "INDPRO", "HOUST", "UMCSENT"}

    if series_id in critical_series:
        return "critical"
    if series_id in high_series:
        return "high"
    return "medium"


def score_jin10_flash(item: dict, config: dict) -> str:
    """Score a Jin10 flash news item."""
    title = (item.get("content") or item.get("title") or "").lower()
    important = item.get("important", False)

    critical_keywords = ["美联储", "降息", "加息", "fomc", "非农", "cpi", "gdp", "衰退",
                         "关税", "tariff", "fed", "powell", "recession"]
    high_keywords = ["pce", "pmi", "就业", "失业", "通胀", "利率", "央行",
                     "ecb", "boj", "制裁", "sanction"]

    for kw in critical_keywords:
        if kw in title:
            return "critical" if important else "high"
    for kw in high_keywords:
        if kw in title:
            return "high"
    if important:
        return "high"
    return "medium"


def score_rss_item(item: dict, config: dict) -> str:
    """Score an RSS news item by source tier and keywords."""
    tier = item.get("source_tier", 3)
    title = (item.get("title") or "").lower()

    critical_keywords = ["fed", "fomc", "rate cut", "rate hike", "recession",
                         "cpi", "nonfarm", "tariff", "crash", "crisis"]
    high_keywords = ["gdp", "inflation", "unemployment", "earnings",
                     "pce", "treasury", "yield", "sanctions"]

    for kw in critical_keywords:
        if kw in title:
            return "critical" if tier == 1 else "high"
    for kw in high_keywords:
        if kw in title:
            return "high" if tier <= 2 else "medium"
    if tier == 1:
        return "medium"
    return "low"


def score_price_anomaly(anomaly: dict, config: dict) -> str:
    """Score a price anomaly — already pre-filtered by threshold."""
    return anomaly.get("severity", "high")


def score_event(event_type: str, event: dict, config: dict) -> str:
    """Route to the appropriate scorer and return impact level."""
    scorers = {
        "fred": score_fred_release,
        "jin10_flash": score_jin10_flash,
        "rss": score_rss_item,
        "price": score_price_anomaly,
    }
    scorer = scorers.get(event_type)
    if scorer is None:
        return "low"
    return scorer(event, config)


def should_notify(level: str) -> bool:
    """Critical and High trigger Agent notification."""
    return level in ("critical", "high")


def should_store(level: str) -> bool:
    """Critical, High, and Medium get stored in PKS."""
    return level in ("critical", "high", "medium")
