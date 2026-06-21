"""RSS/Atom feed scanner."""

import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

ATOM_NS = "{http://www.w3.org/2005/Atom}"


def fetch_feed(url: str, timeout: int = 15) -> list[dict]:
    """Fetch and parse an RSS/Atom feed, return normalized items."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StockAdvisor/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
    except Exception:
        return []

    if root.tag == "rss" or root.find(".//item") is not None:
        return _parse_rss(root)
    if root.tag == f"{ATOM_NS}feed" or root.find(f".//{ATOM_NS}entry") is not None:
        return _parse_atom(root)
    return []


def _parse_rss(root: ET.Element) -> list[dict]:
    items = []
    for item in root.findall(".//item"):
        title = _text(item, "title")
        link = _text(item, "link")
        pub_date = _text(item, "pubDate")
        description = _text(item, "description")
        parsed_time = None
        if pub_date:
            try:
                parsed_time = parsedate_to_datetime(pub_date).isoformat()
            except Exception:
                pass
        items.append({
            "title": title or "",
            "link": link or "",
            "published": parsed_time or pub_date or "",
            "summary": (description or "")[:500],
            "guid": _text(item, "guid") or link or _hash(title),
        })
    return items


def _parse_atom(root: ET.Element) -> list[dict]:
    items = []
    for entry in root.findall(f".//{ATOM_NS}entry"):
        title = _text(entry, f"{ATOM_NS}title")
        link_el = entry.find(f"{ATOM_NS}link")
        link = link_el.get("href", "") if link_el is not None else ""
        published = _text(entry, f"{ATOM_NS}published") or _text(entry, f"{ATOM_NS}updated")
        summary = _text(entry, f"{ATOM_NS}summary") or _text(entry, f"{ATOM_NS}content")
        entry_id = _text(entry, f"{ATOM_NS}id")
        items.append({
            "title": title or "",
            "link": link,
            "published": published or "",
            "summary": (summary or "")[:500],
            "guid": entry_id or link or _hash(title),
        })
    return items


def _text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _hash(s: str | None) -> str:
    return hashlib.md5((s or "").encode()).hexdigest()[:12]


def scan_feeds(feeds_config: list[dict]) -> list[dict]:
    """Scan all configured RSS feeds, return all items with source metadata."""
    all_items = []
    for feed in feeds_config:
        items = fetch_feed(feed["url"])
        for item in items:
            item["source_label"] = feed.get("label", feed["url"])
            item["source_tier"] = feed.get("tier", 3)
        all_items.extend(items)
    return all_items
