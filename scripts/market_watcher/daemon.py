"""Main scheduling loop for market_watcher daemon.

This is the heart of the information management system:
1. Collect data from all sources
2. Score impact
3. Run market overview assessment
4. Run theme analysis + narrative management
5. Write to PKS
6. Notify on critical/high events
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import pks, scorer, trigger
from .core import analyzer, calendar, overview
from .sources import fred, jin10, rss, price

logger = logging.getLogger("market_watcher")

STATE_FILE = Path("data/watcher_state.json")

def _extract_jin10_items(data) -> list:
    if not data:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            return inner.get("items", [])
        if isinstance(inner, list):
            return inner
    return []


SYMBOL_MAP = {
    "^VIX": "vix",
    "^TNX": "ust_10y",
    "^FVX": "ust_5y",
    "^IRX": "ust_2y",
    "DX-Y.NYB": "dxy",
    "GC=F": "gold",
    "CL=F": "oil",
    "HG=F": "copper",
    "^GSPC": "spx",
    "^IXIC": "ndx",
    "^DJI": "dji",
    "^HSI": "hsi",
    "000001.SS": "sse",
    "^N225": "nikkei",
}


def load_config(path: str = "config/watcher.json") -> dict:
    with open(path) as f:
        return json.load(f)


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_scan": {}, "seen_guids": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def is_market_hours(config: dict) -> bool:
    hours_cfg = config.get("notification", {}).get("market_hours", {})
    if not hours_cfg:
        return True
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(hours_cfg.get("timezone", "Asia/Shanghai"))
    except ImportError:
        return True
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return hours_cfg.get("weekend", False)
    start = hours_cfg.get("start", 8)
    end = hours_cfg.get("end", 23)
    return start <= now.hour < end


# --- Source Scanners ---

def scan_fred(config: dict, state: dict) -> list[dict]:
    events = []
    api_key = config["fred"]["api_key"]
    for label, series_id in config["fred"]["series"].items():
        last_date = state.get("last_scan", {}).get(f"fred_{series_id}")
        obs = fred.check_for_new_release(series_id, api_key, last_date)
        if obs:
            obs["label"] = label
            level = scorer.score_event("fred", obs, config)
            if scorer.should_store(level):
                calendar.write_fred_release_to_pks(obs)
                events.append(trigger.format_event("fred", obs, level))
            state.setdefault("last_scan", {})[f"fred_{series_id}"] = obs["date"]
    return events


def scan_jin10(config: dict, state: dict) -> list[dict]:
    events = []
    try:
        client = jin10.create_client(config)
    except Exception as e:
        logger.warning(f"Jin10 client init failed: {e}")
        return []

    # Flash news
    try:
        data = client.list_flash()
        items = _extract_jin10_items(data)
        seen = set(state.get("seen_guids", []))

        for item in (items or []):
            guid = str(item.get("url") or item.get("id") or item.get("remark_id") or hash(str(item)))
            if guid in seen:
                continue
            seen.add(guid)
            level = scorer.score_event("jin10_flash", item, config)
            if scorer.should_store(level):
                content = item.get("content") or item.get("title") or ""
                pks.write_news_item(
                    source_label="jin10",
                    title=content[:200],
                    tier=1 if level in ("critical", "high") else 2,
                    tags=["jin10", level],
                )
                events.append(trigger.format_event("jin10_flash", item, level))

        state["seen_guids"] = list(seen)[-500:]
    except Exception as e:
        logger.warning(f"Jin10 flash scan failed: {e}")

    # Calendar
    try:
        cal_events = calendar.scan_upcoming_events(client)
        calendar.write_events_to_pks(cal_events)
    except Exception as e:
        logger.warning(f"Jin10 calendar scan failed: {e}")

    return events


def scan_rss(config: dict, state: dict) -> list[dict]:
    events = []
    feeds = config.get("rss_feeds", config.get("rss", {}).get("feeds", []))
    items = rss.scan_feeds(feeds)
    seen = set(state.get("seen_guids", []))

    for item in items:
        guid = item.get("guid", "")
        if guid in seen:
            continue
        seen.add(guid)
        level = scorer.score_event("rss", item, config)
        if scorer.should_store(level):
            pks.write_news_item(
                source_label=item.get("source_label", "rss"),
                title=item.get("title", "")[:200],
                tier=item.get("source_tier", 3),
                tags=[level],
            )
            events.append(trigger.format_event("rss", item, level))

    state["seen_guids"] = list(seen)[-500:]
    return events


def scan_prices(config: dict, state: dict) -> tuple[list[dict], dict]:
    """Scan prices. Returns (anomaly_events, price_data_for_overview)."""
    try:
        import yfinance as yf
    except ImportError:
        return [], {}

    symbols = list(SYMBOL_MAP.keys())
    try:
        data = yf.download(symbols, period="2d", progress=False, group_by="ticker")
    except Exception:
        return [], {}

    price_data = {}
    for yf_sym, label in SYMBOL_MAP.items():
        try:
            closes = data[yf_sym]["Close"].dropna()
            if len(closes) >= 2:
                price_data[label] = (float(closes.iloc[-1]), float(closes.iloc[-2]))
        except (KeyError, IndexError):
            continue

    thresholds = config.get("price_alert_thresholds", config.get("price_alerts", {}).get("thresholds", {}))
    anomalies = price.check_anomalies(thresholds)
    events = []
    for a in anomalies:
        level = scorer.score_event("price", a, config)
        if scorer.should_store(level):
            pks.write_price_signal(
                symbol=a["symbol"],
                change=a["change"],
                current=a["current"],
                severity=level,
            )
            events.append(trigger.format_event("price", a, level))

    return events, price_data


# --- Main Cycle ---

def run_scan_cycle(config: dict) -> dict:
    """Run one full scan cycle: collect → score → analyze → write PKS → notify."""
    state = load_state()
    all_events = []
    errors = []
    price_data = {}

    scan_cfg = config.get("scan_intervals", {})
    scanners = {
        "fred": scan_cfg.get("fred_minutes", 60) * 60,
        "jin10_flash": scan_cfg.get("jin10_flash_minutes", 10) * 60,
        "rss": scan_cfg.get("rss_minutes", 30) * 60,
        "price": scan_cfg.get("price_minutes", 15) * 60,
    }

    now = time.time()

    for source_name, interval in scanners.items():
        last_run = state.get("last_scan", {}).get(f"_time_{source_name}", 0)
        if now - last_run < interval:
            continue

        logger.info(f"Scanning {source_name}...")
        try:
            if source_name == "fred":
                events = scan_fred(config, state)
            elif source_name == "jin10_flash":
                events = scan_jin10(config, state)
            elif source_name == "rss":
                events = scan_rss(config, state)
            elif source_name == "price":
                events, price_data = scan_prices(config, state)
            else:
                events = []

            all_events.extend(events)
            state.setdefault("last_scan", {})[f"_time_{source_name}"] = now
        except Exception as e:
            logger.error(f"Error scanning {source_name}: {e}")
            errors.append({"source": source_name, "error": str(e)})

    # Run market overview if we got price data
    overview_signals = []
    if price_data:
        try:
            overview_signals = overview.run_overview(price_data)
            overview.write_signals_to_pks(overview_signals)
        except Exception as e:
            logger.error(f"Overview assessment failed: {e}")
            errors.append({"source": "overview", "error": str(e)})

    # Run theme analysis on collected events + signals
    themes = []
    if all_events or overview_signals:
        try:
            themes = analyzer.run_analysis(all_events, overview_signals)
        except Exception as e:
            logger.error(f"Theme analysis failed: {e}")
            errors.append({"source": "analyzer", "error": str(e)})

    # Run PKS maintenance periodically (every ~6 hours)
    last_maint = state.get("last_scan", {}).get("_time_maintenance", 0)
    if now - last_maint > 21600:
        try:
            maint_result = pks.run_maintenance()
            logger.info(f"PKS maintenance: {maint_result}")
            state.setdefault("last_scan", {})["_time_maintenance"] = now
        except Exception as e:
            logger.warning(f"PKS maintenance failed: {e}")

    save_state(state)

    # Notify on critical/high events
    notify_events = [e for e in all_events if scorer.should_notify(e["level"])]
    if notify_events and is_market_hours(config):
        trigger.notify_agent(notify_events, config)

    return {
        "timestamp": datetime.now().isoformat(),
        "events": len(all_events),
        "signals": len(overview_signals),
        "themes": len(themes),
        "notified": len(notify_events),
        "errors": errors,
    }


def run_daemon(config_path: str = "config/watcher.json"):
    """Main daemon loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    config = load_config(config_path)
    scan_cfg = config.get("scan_intervals", {})
    intervals_sec = [v * 60 for v in scan_cfg.values()] if scan_cfg else [300]
    loop_sleep = max(60, min(intervals_sec) // 2)

    logger.info(f"Market watcher starting. Loop interval: {loop_sleep}s")
    logger.info(f"PKS project: {pks.PROJECT_ID}")

    while True:
        try:
            result = run_scan_cycle(config)
            if result["events"] > 0 or result["signals"] > 0:
                logger.info(
                    f"Cycle: {result['events']} events, "
                    f"{result['signals']} signals, "
                    f"{result['themes']} themes, "
                    f"{result['notified']} notified"
                )
        except Exception as e:
            logger.error(f"Scan cycle failed: {e}")
        time.sleep(loop_sleep)
