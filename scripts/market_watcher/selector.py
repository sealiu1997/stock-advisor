"""Daily selector — picks top facts and inferences from raw material to promote into PKS.

This is the gatekeeper between Layer 1 (daily material) and Layer 2 (durable PKS claims).
Rules:
  - factual claims <= FACTUAL_MAX per day (default 20)
  - inference claims <= INFERENCE_MAX per day (default 5)
  - scoring considers: portfolio relevance, macro importance, price reaction, source tier
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import pks
from .material import MaterialStore

logger = logging.getLogger("market_watcher.selector")

FACTUAL_MAX = 20
INFERENCE_MAX = 5

CRITICAL_MACRO = {
    "cpi", "core cpi", "nfp", "non-farm", "nonfarm", "fomc", "fed",
    "gdp", "pce", "core pce", "unemployment", "fedfunds",
    "美联储", "非农", "cpi", "gdp", "pce", "失业率",
}

HIGH_MACRO = {
    "pmi", "ism", "retail sales", "initial claims", "housing",
    "consumer confidence", "michigan", "industrial production",
    "零售", "pmi", "初请", "消费者信心",
}

ASSET_KEYWORDS = {
    "gold": {"黄金", "gold", "xau"},
    "oil": {"原油", "oil", "crude", "opec", "wti", "brent"},
    "btc": {"btc", "bitcoin", "比特币", "crypto"},
    "copper": {"铜", "copper", "hg"},
}


def _load_portfolio() -> dict:
    path = Path("config/portfolio.json")
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _load_watchlist() -> dict:
    path = Path("config/watchlist.json")
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _build_relevance_keywords() -> set[str]:
    keywords = set()
    portfolio = _load_portfolio()
    watchlist = _load_watchlist()
    for market in portfolio.values():
        for item in market:
            keywords.add(item.get("symbol", "").lower())
            keywords.add(item.get("name", "").lower())
    for market in watchlist.values():
        for item in market:
            keywords.add(item.get("symbol", "").lower())
            keywords.add(item.get("name", "").lower())
    keywords.discard("")
    return keywords


def score_item(item: dict, relevance_keywords: set[str]) -> float:
    """Score a raw material item for PKS promotion. Higher = more important."""
    score = 0.0
    text = (
        str(item.get("content", ""))
        + " " + str(item.get("title", ""))
        + " " + str(item.get("signal", ""))
        + " " + str(item.get("name", ""))
        + " " + str(item.get("label", ""))
    ).lower()

    level = item.get("_level", "medium")
    score += {"critical": 5.0, "high": 3.0, "medium": 1.0, "low": 0.0}.get(level, 0.0)

    for kw in CRITICAL_MACRO:
        if kw in text:
            score += 4.0
            break

    for kw in HIGH_MACRO:
        if kw in text:
            score += 2.0
            break

    for kw in relevance_keywords:
        if len(kw) >= 2 and kw in text:
            score += 3.0
            break

    for asset, kws in ASSET_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                score += 2.0
                break

    tier = item.get("source_tier", item.get("tier", 3))
    if tier == 1:
        score += 1.5
    elif tier == 2:
        score += 0.5

    star = item.get("star", 0)
    if star >= 3:
        score += 2.0

    change_pct = abs(item.get("change_pct", 0))
    if change_pct >= 3.0:
        score += 3.0
    elif change_pct >= 1.5:
        score += 1.5

    if item.get("high_impact"):
        score += 2.0

    return round(score, 1)


def _item_to_fact(item: dict, source: str) -> dict:
    """Convert a raw material item to a fact record for PKS promotion."""
    text = (
        item.get("content")
        or item.get("title")
        or item.get("signal")
        or item.get("name")
        or str(item.get("label", ""))
    )

    tags = ["selected"]
    if source == "fred":
        tags.extend(["macro", "data", "actual_release"])
    elif source == "calendar":
        if item.get("actual"):
            tags.extend(["macro", "actual_release"])
        else:
            tags.extend(["calendar", "scheduled"])
    elif source in ("jin10", "jin10_flash"):
        tags.append("news")
    elif source == "rss":
        tags.append("news")
    elif source in ("prices", "overview"):
        tags.extend(["price", "intraday"])

    metadata = {}
    if source == "calendar":
        metadata = {
            "event_name": item.get("name") or item.get("title", ""),
            "release_time": item.get("pub_time") or item.get("date", ""),
            "previous": item.get("previous", ""),
            "consensus": item.get("consensus", ""),
            "actual": item.get("actual", ""),
            "status": "actual" if item.get("actual") else "scheduled",
        }
    elif source in ("prices", "overview"):
        metadata = {
            "asset": item.get("label") or item.get("commodity") or item.get("index", ""),
            "price": item.get("current", 0),
            "change_pct": item.get("change_pct", 0),
        }
        if item.get("type"):
            metadata["signal_type"] = item["type"]
    elif source == "fred":
        metadata = {
            "series": item.get("series_id", ""),
            "value": item.get("value", ""),
            "date": item.get("date", ""),
        }

    subject = "market"
    predicate = "event"
    if source == "calendar":
        subject = "economic_calendar"
        predicate = "actual_release" if item.get("actual") else "scheduled_event"
    elif source in ("prices", "overview"):
        subject = item.get("label") or item.get("commodity") or item.get("index") or "market"
        predicate = "market_move"
    elif source == "fred":
        subject = item.get("label") or item.get("series_id", "macro")
        predicate = "data_release"
    elif source in ("jin10", "rss"):
        subject = "news"
        predicate = "headline"

    return {
        "subject": subject,
        "predicate": predicate,
        "object": str(text)[:200],
        "content": str(text)[:300],
        "tags": tags,
        "metadata": metadata,
        "source_ref": source,
        "excerpt": str(text)[:200],
        "_score": item.get("_score", 0),
        "_source": source,
    }


def select_daily_facts(
    store: MaterialStore,
    day: date | None = None,
    max_facts: int = FACTUAL_MAX,
) -> list[dict]:
    """Select top factual items from today's material for PKS promotion."""
    day = day or date.today()
    all_data = store.load_all(day)
    relevance_kw = _build_relevance_keywords()

    scored_items = []
    for source, items in all_data.items():
        for item in items:
            s = score_item(item, relevance_kw)
            item["_score"] = s
            item["_source"] = source
            scored_items.append(item)

    scored_items.sort(key=lambda x: x["_score"], reverse=True)
    top = scored_items[:max_facts]

    facts = []
    for item in top:
        if item["_score"] < 2.0:
            break
        facts.append(_item_to_fact(item, item["_source"]))

    return facts


def select_daily_inferences(
    themes: list[dict],
    max_inferences: int = INFERENCE_MAX,
) -> list[dict]:
    """Select top inference candidates from theme analysis results.

    This is the Layer 1 (rules) filter. Layer 2 (agent) can further refine.
    """
    if not themes:
        return []

    inferences = []
    for theme in themes[:max_inferences]:
        evidence_texts = [e["text"][:80] for e in theme.get("evidence", [])[:3]]
        inferences.append({
            "subject": "market_narrative",
            "predicate": "active_theme",
            "object": f"[{theme['driver_description']}] {theme['summary'][:150]}",
            "content": theme["summary"][:300],
            "tags": ["narrative", "selected", theme["driver_type"]],
            "confidence": theme.get("confidence", 0.7),
            "metadata": {
                "driver_type": theme["driver_type"],
                "driver_description": theme["driver_description"],
                "evidence_count": theme.get("evidence_count", 0),
            },
            "source_ref": "market_watcher/selector",
            "excerpt": "; ".join(evidence_texts),
            "_score": theme.get("confidence", 0.7) * 10,
        })

    return inferences


def _supersede_scheduled_events(facts: list[dict]):
    """B3: When actual data arrives for a calendar event, supersede the scheduled claim."""
    actual_events = [
        f for f in facts
        if f.get("_source") == "calendar" and f.get("metadata", {}).get("status") == "actual"
    ]
    if not actual_events:
        return

    scheduled_claims = pks.list_claims(tag="scheduled", subject="economic_calendar")
    if not scheduled_claims:
        return

    for actual in actual_events:
        event_name = actual.get("metadata", {}).get("event_name", "")
        if not event_name:
            continue
        event_lower = event_name.lower()
        for claim in scheduled_claims:
            claim_obj = claim.object if hasattr(claim, "object") else claim.get("object", "")
            if event_lower in claim_obj.lower():
                claim_id = claim.claim_id if hasattr(claim, "claim_id") else claim.get("claim_id", "")
                if claim_id:
                    pks.supersede_claim(
                        claim_id,
                        actual["object"],
                        source_ref="market_watcher/selector",
                        excerpt=actual.get("excerpt", ""),
                        tags=["macro", "actual_release", "selected"],
                    )
                    logger.info(f"Superseded scheduled→actual: {event_name}")
                break


def promote_to_pks(facts: list[dict], inferences: list[dict], day: date | None = None) -> dict:
    """Write selected facts and inferences to PKS and save selection report."""
    day = day or date.today()
    valid_until_short = day + timedelta(days=1)
    valid_until_medium = day + timedelta(days=7)
    valid_until_long = day + timedelta(days=30)

    fact_ids = []
    for fact in facts:
        tags = fact.get("tags", [])
        if "intraday" in tags:
            vu = valid_until_short
        elif "actual_release" in tags:
            vu = valid_until_long
        elif "scheduled" in tags:
            vu = valid_until_short
        else:
            vu = valid_until_medium

        cid = pks.write_selected_fact(
            subject=fact["subject"],
            predicate=fact["predicate"],
            obj=fact["object"],
            tags=tags,
            source_ref=fact.get("source_ref", "market_watcher/selector"),
            excerpt=fact.get("excerpt", ""),
            content=fact.get("content", ""),
            metadata=fact.get("metadata"),
            valid_until=vu,
        )
        if cid:
            fact_ids.append(cid)

    inference_ids = []
    for inf in inferences:
        cid = pks.write_selected_inference(
            subject=inf["subject"],
            predicate=inf["predicate"],
            obj=inf["object"],
            confidence=inf.get("confidence", 0.7),
            tags=inf.get("tags", []),
            source_ref=inf.get("source_ref", "market_watcher/selector"),
            excerpt=inf.get("excerpt", ""),
            content=inf.get("content", ""),
            metadata=inf.get("metadata"),
            valid_until=day + timedelta(days=14),
        )
        if cid:
            inference_ids.append(cid)

    _supersede_scheduled_events(facts)

    report = {
        "date": day.isoformat(),
        "factual_selected": len(fact_ids),
        "inference_selected": len(inference_ids),
        "factual_max": FACTUAL_MAX,
        "inference_max": INFERENCE_MAX,
        "discarded_to_material": max(0, sum(
            len(items) for items in MaterialStore().load_all(day).values()
        ) - len(facts) - len(inferences)),
    }
    logger.info(
        f"Daily selection: {report['factual_selected']} facts, "
        f"{report['inference_selected']} inferences, "
        f"{report['discarded_to_material']} discarded"
    )
    return report


def run_daily_selection(store: MaterialStore | None = None, day: date | None = None) -> dict:
    """Full daily selection pipeline: score material → pick top N → promote to PKS."""
    store = store or MaterialStore()
    day = day or date.today()

    facts = select_daily_facts(store, day)

    from .core.analyzer import analyze_cycle
    all_events = []
    all_signals = []
    all_data = store.load_all(day)
    for source, items in all_data.items():
        for item in items:
            if source in ("overview",):
                all_signals.append(item)
            else:
                desc = (
                    item.get("content")
                    or item.get("title")
                    or item.get("signal")
                    or item.get("name")
                    or ""
                )
                all_events.append({
                    "type": source,
                    "description": desc,
                    "level": item.get("_level", "medium"),
                })
    themes = analyze_cycle(all_events, all_signals)
    inferences = select_daily_inferences(themes)

    report = promote_to_pks(facts, inferences, day)

    store.save_selection("selected_facts.json", facts, day)
    store.save_selection("selected_inferences.json", inferences, day)
    store.save_selection("selection_report.json", report, day)

    return report
