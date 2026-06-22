"""CLI entry point: python -m market_watcher [command]"""

import argparse
import json
import sys


def _extract_jin10_items(data) -> list:
    """Extract items from Jin10 response (handles nested data.items structure)."""
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


def cmd_run(args):
    from .daemon import run_daemon
    run_daemon(config_path=args.config)


def cmd_scan(args):
    from .daemon import load_config, run_scan_cycle
    config = load_config(args.config)
    result = run_scan_cycle(config)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_status(args):
    from .daemon import STATE_FILE
    if not STATE_FILE.exists():
        print("No state file found. Watcher has not run yet.")
        return
    with open(STATE_FILE) as f:
        state = json.load(f)
    last_scans = state.get("last_scan", {})
    print("Last scan times:")
    for k, v in sorted(last_scans.items()):
        if k.startswith("_time_"):
            from datetime import datetime
            t = datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  {k[6:]:20s} {t}")
    seen_ids = state.get("seen_ids", {})
    total_seen = sum(len(v) for v in seen_ids.values()) if isinstance(seen_ids, dict) else 0
    print(f"\nTracked IDs: {total_seen}")
    for source, ids in seen_ids.items():
        print(f"  {source:15s} {len(ids)}")


def cmd_context(args):
    """Show full PKS market context (what daily-briefing would read)."""
    from . import pks
    ctx = pks.render_context()
    if ctx:
        print(ctx)
    else:
        print("No market context available. Run a scan first.")


def cmd_narratives(args):
    from . import pks
    narratives = pks.get_active_narratives()
    if not narratives:
        print("No active narratives.")
        return
    for n in narratives:
        subj = n.subject if hasattr(n, "subject") else n.get("subject", "?")
        obj = n.object if hasattr(n, "object") else n.get("object", "?")
        conf = n.confidence if hasattr(n, "confidence") else n.get("confidence", "?")
        print(f"  [{conf}] {obj}")


def cmd_health(args):
    from . import pks
    report = pks.health_check()
    if not report:
        print("Health check failed or PKS not available.")
        return
    for k, v in report.items():
        print(f"  {k:30s} {v}")


def cmd_maintain(args):
    from . import pks
    result = pks.run_maintenance()
    if not result:
        print("Maintenance failed.")
        return
    print(json.dumps(result, indent=2))


def cmd_material(args):
    from .material import MaterialStore
    store = MaterialStore()
    dates = store.list_dates()
    if not dates:
        print("No material stored yet.")
        return
    from datetime import date
    today = date.today()
    print(f"Material dates: {len(dates)} (keeping 7 days)")
    for d in dates[-7:]:
        stats = store.day_stats(d)
        marker = " ← today" if d == today else ""
        total = sum(stats.values())
        detail = ", ".join(f"{k}:{v}" for k, v in stats.items())
        print(f"  {d.isoformat()}  {total:>4d} items  ({detail}){marker}")


def cmd_test_source(args):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from .daemon import load_config
    config = load_config(args.config)
    source = args.source

    if source == "fred":
        from .sources import fred
        results = fred.scan_all_series(config)
        for r in results:
            print(f"  {r['label']:15s} {r['value']:>10s}  ({r['date']})")

    elif source == "jin10":
        from .sources import jin10
        client = jin10.create_client(config)
        data = client.list_flash()
        items = _extract_jin10_items(data)
        if items:
            for item in items[:10]:
                content = item.get("content") or item.get("title") or str(item)
                ts = item.get("time", "")
                print(f"  [{ts[11:19] if len(ts) > 18 else ts}] {str(content)[:80]}")
        else:
            print("  No data returned.")

    elif source == "jin10-calendar":
        from .sources import jin10
        from .core.calendar import process_jin10_calendar
        client = jin10.create_client(config)
        raw = client.list_calendar()
        events = process_jin10_calendar(raw)
        high = [e for e in events if e["high_impact"]]
        print(f"  Total events: {len(events)}, High impact: {len(high)}")
        for e in high[:10]:
            parts = [e["name"]]
            if e["previous"]:
                parts.append(f"前值:{e['previous']}")
            if e["consensus"]:
                parts.append(f"预期:{e['consensus']}")
            if e["actual"]:
                parts.append(f"实际:{e['actual']}")
            print(f"  {' | '.join(parts)}")

    elif source == "rss":
        from .sources import rss
        feeds = config.get("rss_feeds", config.get("rss", {}).get("feeds", []))
        items = rss.scan_feeds(feeds)
        print(f"  Total items: {len(items)}")
        for item in items[:10]:
            print(f"  [{item.get('source_label', '?')}] {item['title'][:70]}")

    elif source == "price":
        from .sources import price
        thresholds = config.get("price_alert_thresholds", config.get("price_alerts", {}).get("thresholds", {}))
        anomalies = price.check_anomalies(thresholds)
        if anomalies:
            for a in anomalies:
                print(f"  {a['label']:10s} {a['change']}")
        else:
            print("  No anomalies detected.")

    elif source == "overview":
        from .daemon import SYMBOL_MAP
        try:
            import yfinance as yf
        except ImportError:
            print("  yfinance not installed.")
            return
        symbols = list(SYMBOL_MAP.keys())
        data = yf.download(symbols, period="2d", progress=False, group_by="ticker")
        price_data = {}
        for yf_sym, label in SYMBOL_MAP.items():
            try:
                closes = data[yf_sym]["Close"].dropna()
                if len(closes) >= 2:
                    price_data[label] = (float(closes.iloc[-1]), float(closes.iloc[-2]))
            except (KeyError, IndexError):
                continue
        from .core.overview import run_overview
        signals = run_overview(price_data)
        if signals:
            for s in signals:
                print(f"  [{s['type']}] {s['signal']}")
        else:
            print("  No significant signals detected.")

    else:
        print(f"Unknown source: {source}")
        print("Available: fred, jin10, jin10-calendar, rss, price, overview")


def main():
    parser = argparse.ArgumentParser(
        prog="market_watcher",
        description="Stock Advisor Market Watcher — core information management system",
    )
    parser.add_argument("--config", default="config/watcher.json")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Start the daemon loop")
    sub.add_parser("scan", help="Run one scan cycle and exit")
    sub.add_parser("status", help="Show watcher state")
    sub.add_parser("context", help="Show full PKS market context")
    sub.add_parser("narratives", help="Show active narratives")
    sub.add_parser("health", help="PKS health check")
    sub.add_parser("maintain", help="Run PKS maintenance")

    sub.add_parser("material", help="Show today's raw material stats")

    test_p = sub.add_parser("test", help="Test a data source")
    test_p.add_argument("source",
                        help="fred, jin10, jin10-calendar, rss, price, overview")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "run": cmd_run,
        "scan": cmd_scan,
        "status": cmd_status,
        "context": cmd_context,
        "narratives": cmd_narratives,
        "health": cmd_health,
        "maintain": cmd_maintain,
        "material": cmd_material,
        "test": cmd_test_source,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
