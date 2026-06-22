"""Daily raw material storage — Layer 1 of the two-layer architecture.

Raw news, price snapshots, calendar events, and overview signals are stored
as JSONL files under data/daily_materials/YYYY-MM-DD/. These are NOT durable
PKS claims — they serve as the input for the daily selector which picks
the top facts and inferences to promote into PKS.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("market_watcher.material")

MATERIAL_DIR = Path("data/daily_materials")


def stable_id(source: str, title: str, published: str = "") -> str:
    raw = f"{source}:{title}:{published}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class MaterialStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or MATERIAL_DIR

    def _day_dir(self, day: date | None = None) -> Path:
        day = day or date.today()
        return self.base_dir / day.isoformat()

    def append(self, source: str, items: list[dict], day: date | None = None) -> int:
        day_dir = self._day_dir(day)
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"raw_{source}.jsonl"
        written = 0
        with open(path, "a", encoding="utf-8") as f:
            for item in items:
                item["_stored_at"] = datetime.now().isoformat()
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
                written += 1
        if written:
            logger.debug(f"Appended {written} items to {path.name}")
        return written

    def load(self, source: str, day: date | None = None) -> list[dict]:
        path = self._day_dir(day) / f"raw_{source}.jsonl"
        if not path.exists():
            return []
        items = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items

    def load_all(self, day: date | None = None) -> dict[str, list[dict]]:
        day_dir = self._day_dir(day)
        if not day_dir.exists():
            return {}
        result = {}
        for path in sorted(day_dir.glob("raw_*.jsonl")):
            source = path.stem.removeprefix("raw_")
            result[source] = self.load(source, day)
        return result

    def save_selection(self, filename: str, data: Any, day: date | None = None):
        day_dir = self._day_dir(day)
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_selection(self, filename: str, day: date | None = None) -> Any:
        path = self._day_dir(day) / filename
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def list_dates(self) -> list[date]:
        if not self.base_dir.exists():
            return []
        dates = []
        for d in sorted(self.base_dir.iterdir()):
            if d.is_dir():
                try:
                    dates.append(date.fromisoformat(d.name))
                except ValueError:
                    continue
        return dates

    def cleanup(self, keep_days: int = 7):
        today = date.today()
        removed = 0
        for d in self.list_dates():
            if (today - d).days > keep_days:
                shutil.rmtree(self._day_dir(d), ignore_errors=True)
                removed += 1
        if removed:
            logger.info(f"Cleaned up {removed} old material directories")
        return removed

    def day_stats(self, day: date | None = None) -> dict[str, int]:
        all_data = self.load_all(day)
        return {source: len(items) for source, items in all_data.items()}
