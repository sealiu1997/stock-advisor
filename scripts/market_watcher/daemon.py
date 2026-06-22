"""Main scheduling loop for market_watcher daemon.

Two-layer architecture:
1. Collect → Score → Write to daily material (Layer 1)
2. Overview/Theme analysis on material
3. Notify on critical/high events
4. Daily selector promotes top facts/inferences to PKS (Layer 2)
"""

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path

from . import pks, scorer, trigger
from .core import analyzer, calendar, overview
from .material import MaterialStore, stable_id
from .sources import fred, jin10, rss, price

logger = logging.getLogger("market_watcher")

STATE_FILE = Path("data/watcher_state.json")

material = MaterialStore()


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
    return {"last_scan": {}, "seen_ids": {}}


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


# --- Source Scanners (write to material, not PKS) ---

def scan_fred(config: dict, state: dict) -> list[dict]:
    events = []
    api_key = config["fred"]["api_key"]
    material_items = []
    for label, series_id in config["fred"]["series"].items():
        last_date = state.get("last_scan", {}).get(f"fred_{series_id}")
        obs = fred.check_for_new_release(series_id, api_key, last_date)
        if obs:
            obs["label"] = label
            obs["_id"] = stable_id("fred", series_id, obs.get("date", ""))
            level = scorer.score_event("fred", obs, config)
            obs["_level"] = level
            material_items.append(obs)
            if scorer.should_store(level):
                events.append(trigger.format_event("fred", obs, level))
            state.setdefault("last_scan", {})[f"fred_{series_id}"] = obs["date"]

    if material_items:
        material.append("fred", material_items)
    return events


def scan_jin10(config: dict, state: dict) -> list[dict]:
    events = []
    try:
        client = jin10.create_client(config)
    except Exception as e:
        logger.warning(f"Jin10 client init failed: {e}")
        return []

    # Flash news → material
    try:
        data = client.list_flash()
        items = _extract_jin10_items(data)
        seen = state.get("seen_ids", {}).get("jin10", {})

        material_items = []
        for item in (items or []):
            content = item.get("content") or item.get("title") or ""
            sid = stable_id("jin10", content[:100], str(item.get("url", "")))
            if sid in seen:
                continue
            seen[sid] = datetime.now().isoformat()

            level = scorer.score_event("jin10_flash", item, config)
            item["_id"] = sid
            item["_level"] = level
            material_items.append(item)

            if scorer.should_store(level):
                events.append(trigger.format_event("jin10_flash", item, level))

        if material_items:
            material.append("jin10", material_items)

        # Trim seen cache
        if len(seen) > 2000:
            sorted_ids = sorted(seen.items(), key=lambda x: x[1], reverse=True)
            seen = dict(sorted_ids[:1000])
        state.setdefault("seen_ids", {})["jin10"] = seen
    except Exception as e:
        logger.warning(f"Jin10 flash scan failed: {e}")

    # Calendar → material
    try:
        cal_events = calendar.scan_upcoming_events(client)
        if cal_events:
            cal_items = []
            for ev in cal_events:
                ev["_id"] = stable_id(
                    "calendar",
                    ev.get("title", ""),
                    ev.get("pub_time", ""),
                )
                cal_items.append(ev)
            material.append("calendar", cal_items)
    except Exception as e:
        logger.warning(f"Jin10 calendar scan failed: {e}")

    return events


def scan_rss(config: dict, state: dict) -> list[dict]:
    events = []
    feeds = config.get("rss_feeds", config.get("rss", {}).get("feeds", []))
    items = rss.scan_feeds(feeds)
    seen = state.get("seen_ids", {}).get("rss", {})

    material_items = []
    for item in items:
        title = item.get("title", "")
        link = item.get("link", "")
        sid = stable_id("rss", title, link)
        if sid in seen:
            continue
        seen[sid] = datetime.now().isoformat()

        level = scorer.score_event("rss", item, config)
        item["_id"] = sid
        item["_level"] = level
        material_items.append(item)

        if scorer.should_store(level):
            events.append(trigger.format_event("rss", item, level))

    if material_items:
        material.append("rss", material_items)

    if len(seen) > 2000:
        sorted_ids = sorted(seen.items(), key=lambda x: x[1], reverse=True)
        seen = dict(sorted_ids[:1000])
    state.setdefault("seen_ids", {})["rss"] = seen
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
    price_items = []
    for yf_sym, label in SYMBOL_MAP.items():
        try:
            closes = data[yf_sym]["Close"].dropna()
            if len(closes) >= 2:
                current = float(closes.iloc[-1])
                previous = float(closes.iloc[-2])
                price_data[label] = (current, previous)
                pct = (current - previous) / previous * 100
                price_items.append({
                    "_id": stable_id("price", label, date.today().isoformat()),
                    "symbol": yf_sym,
                    "label": label,
                    "current": current,
                    "previous": previous,
                    "change_pct": round(pct, 2),
                })
        except (KeyError, IndexError):
            continue

    if price_items:
        material.append("prices", price_items)

    thresholds = config.get("price_alert_thresholds", config.get("price_alerts", {}).get("thresholds", {}))
    anomalies = price.check_anomalies(thresholds)
    events = []
    for a in anomalies:
        level = scorer.score_event("price", a, config)
        if scorer.should_store(level):
            events.append(trigger.format_event("price", a, level))

    return events, price_data


# --- Main Cycle ---

def run_scan_cycle(config: dict) -> dict:
    """Run one full scan cycle: collect → score → write material → analyze → notify."""
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

    # Run market overview → material (not PKS)
    overview_signals = []
    if price_data:
        try:
            overview_signals = overview.run_overview(price_data)
            if overview_signals:
                overview_items = []
                for sig in overview_signals:
                    sig["_id"] = stable_id(
                        "overview",
                        sig.get("type", ""),
                        date.today().isoformat(),
                    )
                    sig["_type"] = "factual"
                    overview_items.append(sig)
                material.append("overview", overview_items)
        except Exception as e:
            logger.error(f"Overview assessment failed: {e}")
            errors.append({"source": "overview", "error": str(e)})

    # Run theme analysis on collected events + signals → material
    themes = []
    if all_events or overview_signals:
        try:
            themes = analyzer.run_analysis(all_events, overview_signals)
        except Exception as e:
            logger.error(f"Theme analysis failed: {e}")
            errors.append({"source": "analyzer", "error": str(e)})

    # PKS maintenance periodically (every ~6 hours)
    last_maint = state.get("last_scan", {}).get("_time_maintenance", 0)
    if now - last_maint > 21600:
        try:
            maint_result = pks.run_maintenance()
            logger.info(f"PKS maintenance: {maint_result}")
            state.setdefault("last_scan", {})["_time_maintenance"] = now
        except Exception as e:
            logger.warning(f"PKS maintenance failed: {e}")

    # Daily material cleanup (keep 7 days)
    last_cleanup = state.get("last_scan", {}).get("_time_cleanup", 0)
    if now - last_cleanup > 86400:
        try:
            material.cleanup(keep_days=7)
            state.setdefault("last_scan", {})["_time_cleanup"] = now
        except Exception as e:
            logger.warning(f"Material cleanup failed: {e}")

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
    logger.info(f"Material dir: {material.base_dir}")

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
