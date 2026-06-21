"""Theme analyzer — identifies market themes from collected data and manages narratives.

This is the analytical brain of market_watcher. It takes raw events/signals
and constructs structured narratives in PKS.
"""

from __future__ import annotations

import logging
from typing import Any

from .. import pks

logger = logging.getLogger("market_watcher.analyzer")

DRIVER_TYPES = {
    "macro_data": {
        "keywords": ["cpi", "nfp", "gdp", "pce", "pmi", "就业", "通胀",
                      "消费", "retail", "housing", "employment"],
        "description": "宏观数据驱动",
    },
    "rates": {
        "keywords": ["yield", "利率", "fed", "fomc", "降息", "加息",
                      "treasury", "美债", "rate"],
        "description": "利率驱动",
    },
    "geopolitical": {
        "keywords": ["tariff", "关税", "sanction", "制裁", "war", "战争",
                      "election", "选举", "geopolitical"],
        "description": "地缘政治驱动",
    },
    "commodity": {
        "keywords": ["oil", "gold", "原油", "黄金", "copper", "铜",
                      "commodity", "opec"],
        "description": "商品驱动",
    },
    "sector": {
        "keywords": ["ai", "chip", "semiconductor", "半导体", "ev", "电动车",
                      "pharma", "biotech", "tech"],
        "description": "行业驱动",
    },
    "risk_event": {
        "keywords": ["crash", "crisis", "recession", "衰退", "暴跌",
                      "panic", "恐慌", "崩盘", "default", "bank run"],
        "description": "风险事件驱动",
    },
}


def classify_driver(text: str) -> str | None:
    """Classify text into a driver type. Returns driver key or None."""
    text_lower = text.lower()
    scores = {}
    for driver, cfg in DRIVER_TYPES.items():
        score = sum(1 for kw in cfg["keywords"] if kw in text_lower)
        if score > 0:
            scores[driver] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


def analyze_cycle(events: list[dict], signals: list[dict]) -> list[dict]:
    """Analyze a batch of events and signals to identify emerging themes.

    Args:
        events: list of scored events from daemon scan cycle
        signals: list of overview signals from core/overview.py

    Returns:
        list of theme dicts with driver_type, description, evidence, confidence
    """
    theme_candidates = {}

    for event in events:
        desc = event.get("description", "")
        driver = classify_driver(desc)
        if driver:
            theme_candidates.setdefault(driver, []).append({
                "source": event.get("type", "unknown"),
                "text": desc,
                "level": event.get("level", "medium"),
            })

    for signal in signals:
        sig_text = signal.get("signal", "")
        driver = classify_driver(sig_text)
        if driver:
            theme_candidates.setdefault(driver, []).append({
                "source": "overview",
                "text": sig_text,
                "level": "high" if signal.get("type") in ("vix_regime", "yield_curve") else "medium",
            })

    themes = []
    for driver, evidence_list in theme_candidates.items():
        critical_count = sum(1 for e in evidence_list if e["level"] == "critical")
        high_count = sum(1 for e in evidence_list if e["level"] == "high")

        if critical_count > 0:
            confidence = 0.9
        elif high_count >= 2:
            confidence = 0.8
        elif high_count >= 1:
            confidence = 0.7
        elif len(evidence_list) >= 3:
            confidence = 0.6
        else:
            confidence = 0.5

        if confidence < 0.6:
            continue

        driver_desc = DRIVER_TYPES[driver]["description"]
        top_evidence = sorted(evidence_list,
                              key=lambda e: {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(e["level"], 0),
                              reverse=True)[:3]
        summary = "; ".join(e["text"][:60] for e in top_evidence)

        themes.append({
            "driver_type": driver,
            "driver_description": driver_desc,
            "confidence": confidence,
            "evidence_count": len(evidence_list),
            "summary": summary,
            "evidence": top_evidence,
        })

    themes.sort(key=lambda t: t["confidence"], reverse=True)
    return themes[:3]


def update_narratives(themes: list[dict]):
    """Compare detected themes against existing PKS narratives and update.

    - Theme matches existing narrative → verify (refresh)
    - Theme is new → write new narrative
    - Existing narrative has no matching theme this cycle → do nothing (let it stale naturally)
    """
    existing = pks.get_active_narratives()
    existing_drivers = {}
    for claim in existing:
        driver = None
        for tag in (claim.tags if hasattr(claim, 'tags') else []):
            if tag in DRIVER_TYPES:
                driver = tag
                break
        if driver:
            existing_drivers[driver] = claim

    for theme in themes:
        driver = theme["driver_type"]

        if driver in existing_drivers:
            claim = existing_drivers[driver]
            claim_id = claim.claim_id if hasattr(claim, 'claim_id') else str(claim)
            pks.verify_claim(claim_id)
            logger.info(f"Verified existing narrative: {driver}")
        else:
            pks.add_claim(
                subject="market_narrative",
                predicate="active_theme",
                obj=f"[{theme['driver_description']}] {theme['summary']}",
                claim_type="inference",
                confidence=theme["confidence"],
                tags=["narrative", driver],
                source_ref="market_watcher/analyzer",
                excerpt=theme["summary"],
            )
            logger.info(f"New narrative: {driver} (confidence={theme['confidence']:.1f})")


def run_analysis(events: list[dict], signals: list[dict]):
    """Full analysis cycle: detect themes → update PKS narratives."""
    themes = analyze_cycle(events, signals)
    if themes:
        logger.info(f"Detected {len(themes)} themes: "
                     f"{', '.join(t['driver_type'] for t in themes)}")
        update_narratives(themes)
    return themes
