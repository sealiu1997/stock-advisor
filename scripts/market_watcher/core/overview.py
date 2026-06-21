"""Market overview — periodic macro signal assessment.

Replaces the standalone market-overview skill with a programmatic engine
that writes structured signals to PKS.
"""

from __future__ import annotations

import logging
from typing import Any

from .. import pks

logger = logging.getLogger("market_watcher.overview")


def assess_vix(current: float, previous: float) -> dict | None:
    """Assess VIX level and regime."""
    if current < 15:
        regime = "low_vol"
        signal = "市场波动率极低，风险偏好高"
    elif current < 20:
        regime = "normal"
        signal = "市场波动率正常"
    elif current < 25:
        regime = "elevated"
        signal = "市场波动率偏高，风险意识上升"
    else:
        regime = "panic"
        signal = "市场处于恐慌状态"

    change = current - previous
    if abs(change) < 1.0 and regime == "normal":
        return None

    return {
        "type": "vix_regime",
        "regime": regime,
        "level": current,
        "change": change,
        "signal": f"VIX {current:.1f} ({change:+.1f}): {signal}",
    }


def assess_yield_curve(rates: dict[str, tuple[float, float]]) -> dict | None:
    """Assess treasury yield curve shape and changes.
    rates: {"2y": (current, previous), "5y": ..., "10y": ...}
    """
    if "2y" not in rates or "10y" not in rates:
        return None

    curr_2y, prev_2y = rates["2y"]
    curr_10y, prev_10y = rates["10y"]

    spread_2s10s = (curr_10y - curr_2y) * 100  # in bp
    spread_change = ((curr_10y - curr_2y) - (prev_10y - prev_2y)) * 100

    bp_10y = (curr_10y - prev_10y) * 100

    if abs(bp_10y) < 3 and abs(spread_change) < 3:
        return None

    if spread_2s10s < 0:
        curve_shape = "inverted"
        signal = f"收益率曲线倒挂 ({spread_2s10s:.0f}bp)，衰退预警"
    elif spread_2s10s < 20:
        curve_shape = "flat"
        signal = f"收益率曲线平坦 ({spread_2s10s:.0f}bp)"
    else:
        curve_shape = "normal"
        signal = f"收益率曲线正常 ({spread_2s10s:.0f}bp)"

    return {
        "type": "yield_curve",
        "curve_shape": curve_shape,
        "spread_2s10s_bp": round(spread_2s10s),
        "bp_10y_change": round(bp_10y),
        "signal": f"10Y {curr_10y:.2f}% ({bp_10y:+.0f}bp), 2s10s {spread_2s10s:.0f}bp: {signal}",
    }


def assess_dxy(current: float, previous: float) -> dict | None:
    """Assess dollar index direction."""
    pct = (current - previous) / previous * 100
    if abs(pct) < 0.3:
        return None

    direction = "strengthening" if pct > 0 else "weakening"
    implications = []
    if pct > 0.5:
        implications = ["利空新兴市场", "利空黄金", "利空大宗商品"]
    elif pct < -0.5:
        implications = ["利好新兴市场", "利好黄金", "利好大宗商品"]

    return {
        "type": "dxy_direction",
        "direction": direction,
        "change_pct": round(pct, 2),
        "signal": f"DXY {current:.1f} ({pct:+.1f}%): 美元{('走强' if pct > 0 else '走弱')}",
        "implications": implications,
    }


def assess_commodities(data: dict[str, tuple[float, float]]) -> list[dict]:
    """Assess commodity moves. data: {"gold": (current, prev), "oil": ...}"""
    signals = []
    thresholds = {"gold": 1.0, "oil": 2.0, "copper": 2.0}

    for commodity, (current, previous) in data.items():
        pct = (current - previous) / previous * 100
        threshold = thresholds.get(commodity, 1.5)
        if abs(pct) < threshold:
            continue

        labels = {"gold": "黄金", "oil": "原油", "copper": "铜"}
        label = labels.get(commodity, commodity)
        signals.append({
            "type": "commodity_move",
            "commodity": commodity,
            "change_pct": round(pct, 2),
            "signal": f"{label} {current:.1f} ({pct:+.1f}%)",
        })

    return signals


def assess_indices(data: dict[str, tuple[float, float]]) -> list[dict]:
    """Assess major index divergences. data: {"spx": (curr, prev), ...}"""
    signals = []
    labels = {
        "spx": "标普500", "ndx": "纳斯达克", "dji": "道琼斯",
        "hsi": "恒指", "sse": "上证", "nikkei": "日经",
    }

    changes = {}
    for idx, (current, previous) in data.items():
        pct = (current - previous) / previous * 100
        changes[idx] = pct

    us_indices = [changes.get(k, 0) for k in ("spx", "ndx", "dji") if k in changes]
    if us_indices:
        avg_us = sum(us_indices) / len(us_indices)
        max_div = max(abs(c - avg_us) for c in us_indices) if len(us_indices) > 1 else 0

        if max_div > 1.0:
            signals.append({
                "type": "index_divergence",
                "signal": "美股主要指数出现分化",
                "details": {k: f"{changes[k]:+.1f}%" for k in ("spx", "ndx", "dji") if k in changes},
            })

    for idx, pct in changes.items():
        if abs(pct) >= 1.5:
            signals.append({
                "type": "index_move",
                "index": idx,
                "change_pct": round(pct, 2),
                "signal": f"{labels.get(idx, idx)} {pct:+.1f}%",
            })

    return signals


def run_overview(price_data: dict[str, tuple[float, float]]) -> list[dict]:
    """Run full market overview assessment.

    price_data keys use standard labels:
        "vix", "ust_2y", "ust_5y", "ust_10y", "dxy",
        "gold", "oil", "spx", "ndx", "dji", "hsi", ...

    Values are (current_price, previous_price) tuples.
    Returns list of signal dicts.
    """
    all_signals = []

    if "vix" in price_data:
        sig = assess_vix(*price_data["vix"])
        if sig:
            all_signals.append(sig)

    rates = {}
    for tenor in ("2y", "5y", "10y"):
        key = f"ust_{tenor}"
        if key in price_data:
            rates[tenor] = price_data[key]
    if rates:
        sig = assess_yield_curve(rates)
        if sig:
            all_signals.append(sig)

    if "dxy" in price_data:
        sig = assess_dxy(*price_data["dxy"])
        if sig:
            all_signals.append(sig)

    commodities = {k: v for k, v in price_data.items() if k in ("gold", "oil", "copper")}
    all_signals.extend(assess_commodities(commodities))

    indices = {k: v for k, v in price_data.items()
               if k in ("spx", "ndx", "dji", "hsi", "sse", "nikkei")}
    all_signals.extend(assess_indices(indices))

    return all_signals


def write_signals_to_pks(signals: list[dict]):
    """Write overview signals to PKS."""
    for sig in signals:
        pks.write_market_signal(
            signal_type=sig["type"],
            description=sig["signal"],
            confidence=0.9,
            tags=["overview", sig["type"]],
        )
    if signals:
        logger.info(f"Wrote {len(signals)} overview signals to PKS")
