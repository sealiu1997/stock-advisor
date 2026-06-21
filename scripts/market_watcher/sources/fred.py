"""FRED (Federal Reserve Economic Data) API client."""

import json
import urllib.request
from datetime import datetime, timedelta

BASE_URL = "https://api.stlouisfed.org/fred"


def get_latest_observation(series_id: str, api_key: str) -> dict | None:
    """Fetch the most recent observation for a FRED series."""
    url = (
        f"{BASE_URL}/series/observations"
        f"?series_id={series_id}"
        f"&api_key={api_key}"
        f"&file_type=json"
        f"&sort_order=desc"
        f"&limit=1"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        obs = data.get("observations", [])
        if not obs:
            return None
        return {
            "series_id": series_id,
            "date": obs[0]["date"],
            "value": obs[0]["value"],
            "realtime_start": obs[0].get("realtime_start"),
        }
    except Exception:
        return None


def get_recent_observations(series_id: str, api_key: str, count: int = 6) -> list[dict]:
    """Fetch recent observations for trend analysis."""
    url = (
        f"{BASE_URL}/series/observations"
        f"?series_id={series_id}"
        f"&api_key={api_key}"
        f"&file_type=json"
        f"&sort_order=desc"
        f"&limit={count}"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        return [
            {"date": o["date"], "value": o["value"]}
            for o in data.get("observations", [])
            if o["value"] != "."
        ]
    except Exception:
        return []


def get_series_info(series_id: str, api_key: str) -> dict | None:
    """Fetch metadata about a FRED series (title, frequency, units)."""
    url = (
        f"{BASE_URL}/series"
        f"?series_id={series_id}"
        f"&api_key={api_key}"
        f"&file_type=json"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        seriess = data.get("seriess", [])
        if not seriess:
            return None
        s = seriess[0]
        return {
            "id": s["id"],
            "title": s["title"],
            "frequency": s.get("frequency_short", ""),
            "units": s.get("units_short", ""),
            "last_updated": s.get("last_updated", ""),
        }
    except Exception:
        return None


def check_for_new_release(series_id: str, api_key: str, last_known_date: str | None) -> dict | None:
    """Check if a new data point has been released since last_known_date.
    Returns the new observation if found, None otherwise."""
    latest = get_latest_observation(series_id, api_key)
    if latest is None:
        return None
    if last_known_date is None or latest["date"] > last_known_date:
        return latest
    return None


def scan_all_series(config: dict) -> list[dict]:
    """Scan all configured FRED series for new releases.
    Returns list of new observations found."""
    api_key = config["fred"]["api_key"]
    series_map = config["fred"]["series"]
    results = []
    for label, series_id in series_map.items():
        latest = get_latest_observation(series_id, api_key)
        if latest:
            latest["label"] = label
            results.append(latest)
    return results
