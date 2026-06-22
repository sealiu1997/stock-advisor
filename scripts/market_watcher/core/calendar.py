"""Economic calendar monitoring — absorbs event-calendar skill's detection logic.

Scans Jin10 calendar + FRED release dates, writes upcoming events to PKS,
generates pre-event alerts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from .. import pks

logger = logging.getLogger("market_watcher.calendar")

HIGH_IMPACT_EVENTS = {
    "美国CPI", "美国核心CPI", "CPI", "Core CPI",
    "非农就业", "Non-Farm", "NFP", "Nonfarm",
    "美联储利率决议", "FOMC", "Fed Rate",
    "美国GDP", "GDP",
    "PCE物价指数", "Core PCE", "PCE",
    "初请失业金", "Jobless Claims",
    "PMI", "ISM",
    "密歇根消费者信心", "Michigan",
    "零售销售", "Retail Sales",
}


def is_high_impact(event_name: str) -> bool:
    name_lower = event_name.lower()
    for keyword in HIGH_IMPACT_EVENTS:
        if keyword.lower() in name_lower:
            return True
    return False


def process_jin10_calendar(calendar_data: Any) -> list[dict]:
    """Process Jin10 calendar data into structured events."""
    if not calendar_data:
        return []

    if isinstance(calendar_data, list):
        items = calendar_data
    elif isinstance(calendar_data, dict):
        items = calendar_data.get("data", [])
        if isinstance(items, dict):
            items = items.get("items", [])
    else:
        return []

    events = []
    for item in items:
        name = item.get("title") or item.get("event_name") or item.get("name") or ""
        event_date = item.get("pub_time") or item.get("date") or ""
        previous = item.get("previous") or item.get("former") or ""
        consensus = item.get("consensus") or item.get("forecast") or ""
        actual = item.get("actual") or ""
        star = item.get("star", 0)

        if not name:
            continue

        event = {
            "name": name,
            "date": event_date,
            "previous": str(previous) if previous else "",
            "consensus": str(consensus) if consensus else "",
            "actual": str(actual) if actual else "",
            "star": star,
            "high_impact": is_high_impact(name) or star >= 3,
        }
        events.append(event)

    return events


def scan_upcoming_events(jin10_client, hours_ahead: int = 48) -> list[dict]:
    """Scan for upcoming high-impact economic events."""
    try:
        raw = jin10_client.list_calendar()
        events = process_jin10_calendar(raw)
    except Exception as e:
        logger.warning(f"Calendar scan failed: {e}")
        return []

    upcoming = []
    for event in events:
        if event["high_impact"]:
            upcoming.append(event)

    return upcoming


def check_fred_releases(fred_results: list[dict], state: dict) -> list[dict]:
    """Check FRED scan results for new data releases (post-event detection)."""
    new_releases = []
    for obs in fred_results:
        series_id = obs.get("series_id", "")
        last_known = state.get("last_scan", {}).get(f"fred_{series_id}")
        if last_known is None or obs.get("date", "") > last_known:
            new_releases.append(obs)
    return new_releases


def write_events_to_pks(events: list[dict]):
    """Legacy: write calendar events to PKS. Kept for backward compat / manual use."""
    written = 0
    for event in events:
        if not event.get("high_impact"):
            continue
        details = f"前值: {event['previous']}"
        if event.get("consensus"):
            details += f", 预期: {event['consensus']}"
        if event.get("actual"):
            details += f", 实际: {event['actual']}"

        pks.write_calendar_event(
            event_name=event["name"],
            event_date=event.get("date", ""),
            details=details,
        )
        written += 1

    if written:
        logger.info(f"Wrote {written} calendar events to PKS")


def write_fred_release_to_pks(obs: dict):
    """Legacy: write FRED release to PKS. Kept for backward compat / manual use."""
    label = obs.get("label", obs.get("series_id", "unknown"))
    pks.write_data_point(
        subject=label,
        predicate="reading",
        value=obs["value"],
        period=obs["date"],
        source_ref="FRED",
        tags=["fred"],
    )
    logger.info(f"FRED release: {label} = {obs['value']} ({obs['date']})")
