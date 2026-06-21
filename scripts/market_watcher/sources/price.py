"""Price anomaly detection via yfinance."""

from typing import Any


def check_anomalies(thresholds: dict, portfolio_path: str = "config/portfolio.json") -> list[dict]:
    """Check framework symbols and portfolio for price anomalies.
    Returns list of anomalies that exceed configured thresholds."""
    import json
    try:
        import yfinance as yf
    except ImportError:
        return []

    framework = {
        "^VIX": ("vix_level", "vix_level_high"),
        "^TNX": ("ust_10y", "ust_10y_daily_bp"),
        "GC=F": ("gold", "gold_pct"),
        "CL=F": ("oil", "oil_pct"),
        "^GSPC": ("spx", "index_pct"),
        "^IXIC": ("ndx", "index_pct"),
        "^HSI": ("hsi", "index_pct"),
    }

    anomalies = []

    symbols = list(framework.keys())
    try:
        data = yf.download(symbols, period="2d", progress=False, group_by="ticker")
    except Exception:
        return []

    for symbol, (label, threshold_key) in framework.items():
        try:
            if len(symbols) == 1:
                closes = data["Close"].dropna()
            else:
                closes = data[symbol]["Close"].dropna()
            if len(closes) < 2:
                continue
            current = float(closes.iloc[-1])
            previous = float(closes.iloc[-2])

            if "bp" in threshold_key:
                change = (current - previous) * 100
                change_display = f"{change:+.0f}bp"
                exceeded = abs(change) >= thresholds.get(threshold_key, 999)
            elif "level" in threshold_key:
                change = current
                change_display = f"{current:.1f}"
                exceeded = current >= thresholds.get(threshold_key, 999)
            else:
                change = (current - previous) / previous * 100
                change_display = f"{change:+.1f}%"
                exceeded = abs(change) >= thresholds.get(threshold_key, 999)

            if exceeded:
                anomalies.append({
                    "symbol": symbol,
                    "label": label,
                    "current": current,
                    "previous": previous,
                    "change": change_display,
                    "threshold_key": threshold_key,
                    "severity": "critical" if abs(change) >= thresholds.get(threshold_key, 999) * 1.5 else "high",
                })
        except (KeyError, IndexError, TypeError):
            continue

    try:
        with open(portfolio_path) as f:
            portfolio = json.load(f)
        stock_threshold = thresholds.get("portfolio_stock_pct", 5.0)
        for market, stocks in portfolio.items():
            for stock in stocks:
                sym = stock["symbol"]
                yf_sym = f"{sym}.HK" if market == "HK" else sym
                if market == "CRYPTO":
                    continue
                try:
                    t = yf.Ticker(yf_sym)
                    hist = t.history(period="2d")
                    if len(hist) < 2:
                        continue
                    curr = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2])
                    pct = (curr - prev) / prev * 100
                    if abs(pct) >= stock_threshold:
                        anomalies.append({
                            "symbol": sym,
                            "label": stock.get("name", sym),
                            "current": curr,
                            "previous": prev,
                            "change": f"{pct:+.1f}%",
                            "threshold_key": "portfolio_stock_pct",
                            "severity": "high",
                        })
                except Exception:
                    continue
    except Exception:
        pass

    return anomalies
