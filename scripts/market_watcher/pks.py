"""PKS integration — uses Python API directly (PKS installed locally).

In the two-layer architecture, raw news does NOT go through this module.
Only the daily selector calls write functions here to promote selected
facts and inferences into durable PKS claims.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger("market_watcher.pks")

_kernel = None
PROJECT_ID = "market-context"


def _get_kernel():
    global _kernel
    if _kernel is None:
        from pks.kernel import Kernel
        _kernel = Kernel()
    return _kernel


def _today() -> date:
    return date.today()


def add_claim(
    subject: str,
    predicate: str,
    obj: str,
    *,
    claim_type: str = "factual",
    confidence: float = 1.0,
    tags: list[str] | None = None,
    source_ref: str = "market_watcher",
    excerpt: str = "",
    content: str = "",
    metadata: dict[str, Any] | None = None,
    valid_until: date | None = None,
) -> str | None:
    """Add a new claim to PKS. Returns claim_id or None on failure."""
    kernel = _get_kernel()
    try:
        claim_data: dict[str, Any] = {
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "type": claim_type,
            "confidence": confidence,
            "tags": tags or [],
            "content": content,
            "created_by": "market_watcher",
            "evidence": [
                {
                    "source_ref": source_ref,
                    "relation": "supports",
                    "excerpt": excerpt or obj,
                }
            ],
        }
        if metadata:
            claim_data["metadata"] = metadata
        if valid_until:
            claim_data["valid_until"] = valid_until.isoformat()
        claim = kernel.build_candidate_claim(PROJECT_ID, claim_data)
        decision = kernel.submit_candidate(PROJECT_ID, claim)
        if decision.action.value == "auto_accept":
            kernel.accept_candidate(PROJECT_ID, claim.claim_id)
        logger.debug(f"Claim {claim.claim_id}: {decision.action} ({decision.reason})")
        return claim.claim_id
    except Exception as e:
        logger.error(f"Failed to add claim: {e}")
        return None


def list_claims(
    status: str | None = "accepted",
    claim_type: str | None = None,
    tag: str | None = None,
    subject: str | None = None,
    predicate: str | None = None,
) -> list:
    kernel = _get_kernel()
    try:
        return kernel.list_claims(
            PROJECT_ID,
            status=status,
            type=claim_type,
            tag=tag,
            subject=subject,
            predicate=predicate,
        )
    except Exception as e:
        logger.error(f"Failed to list claims: {e}")
        return []


def expire_claim(claim_id: str) -> bool:
    kernel = _get_kernel()
    try:
        kernel.expire_claim(PROJECT_ID, claim_id)
        return True
    except Exception as e:
        logger.error(f"Failed to expire {claim_id}: {e}")
        return False


def verify_claim(claim_id: str) -> bool:
    kernel = _get_kernel()
    try:
        kernel.verify_claim(PROJECT_ID, claim_id)
        return True
    except Exception as e:
        logger.error(f"Failed to verify {claim_id}: {e}")
        return False


def supersede_claim(
    old_claim_id: str,
    new_object: str,
    *,
    source_ref: str = "market_watcher",
    excerpt: str = "",
    confidence: float = 1.0,
    tags: list[str] | None = None,
) -> str | None:
    kernel = _get_kernel()
    try:
        old = kernel.load_claim(PROJECT_ID, old_claim_id)
        from pks.models import Claim, Evidence, Relation
        new_id = kernel.registry.next_claim_id(old.type_value)
        new_claim = Claim(
            claim_id=new_id,
            subject=old.subject,
            predicate=old.predicate,
            object=new_object,
            type=old.type,
            domain=old.domain,
            tags=tags or old.tags,
            confidence=confidence,
            created_by="market_watcher",
            evidence=[
                Evidence(
                    source_ref=source_ref,
                    relation=Relation.SUPERSEDES,
                    excerpt=excerpt or new_object,
                )
            ],
        )
        result = kernel.supersede_claim(PROJECT_ID, old_claim_id, new_claim)
        return result.claim_id
    except Exception as e:
        logger.error(f"Failed to supersede {old_claim_id}: {e}")
        return None


def health_check() -> dict:
    kernel = _get_kernel()
    try:
        report = kernel.health_check(PROJECT_ID)
        return report.as_summary()
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {}


def run_maintenance() -> dict:
    kernel = _get_kernel()
    try:
        report = kernel.maintenance.run_all(PROJECT_ID, today=_today())
        return {
            "stale_found": report.stale_found,
            "expired_enforced": report.expired_enforced,
            "evidence_issues_found": report.evidence_issues_found,
            "projections_refreshed": report.projections_refreshed,
        }
    except Exception as e:
        logger.error(f"Maintenance failed: {e}")
        return {}


def render_context() -> str:
    kernel = _get_kernel()
    try:
        return kernel.render_context(PROJECT_ID)
    except Exception as e:
        logger.error(f"Render context failed: {e}")
        return ""


# --- High-level helpers for selected claims (Layer 2) ---

def write_selected_fact(
    subject: str,
    predicate: str,
    obj: str,
    *,
    tags: list[str] | None = None,
    source_ref: str = "market_watcher/selector",
    excerpt: str = "",
    content: str = "",
    metadata: dict[str, Any] | None = None,
    valid_until: date | None = None,
) -> str | None:
    """Write a daily-selected factual claim to PKS."""
    return add_claim(
        subject=subject,
        predicate=predicate,
        obj=obj,
        claim_type="factual",
        confidence=1.0,
        tags=tags or [],
        source_ref=source_ref,
        excerpt=excerpt,
        content=content,
        metadata=metadata,
        valid_until=valid_until,
    )


def write_selected_inference(
    subject: str,
    predicate: str,
    obj: str,
    *,
    confidence: float = 0.8,
    tags: list[str] | None = None,
    source_ref: str = "market_watcher/selector",
    excerpt: str = "",
    content: str = "",
    metadata: dict[str, Any] | None = None,
    valid_until: date | None = None,
) -> str | None:
    """Write a daily-selected inference claim to PKS."""
    return add_claim(
        subject=subject,
        predicate=predicate,
        obj=obj,
        claim_type="inference",
        confidence=confidence,
        tags=["narrative"] + (tags or []),
        source_ref=source_ref,
        excerpt=excerpt,
        content=content,
        metadata=metadata,
        valid_until=valid_until,
    )


# --- Legacy helpers (kept for backward compat / CLI test commands) ---

def write_data_point(subject: str, predicate: str, value: str,
                     period: str, source_ref: str = "market_watcher",
                     tags: list[str] | None = None) -> str | None:
    return add_claim(
        subject=subject,
        predicate=predicate,
        obj=value,
        claim_type="factual",
        confidence=1.0,
        tags=["macro", "data"] + (tags or []),
        source_ref=source_ref,
        excerpt=f"{subject} {predicate}: {value} ({period})",
        content=f"{subject} {predicate} = {value}, period {period}",
    )


def write_price_signal(symbol: str, change: str, current: float,
                       severity: str) -> str | None:
    label = symbol.lower().replace("^", "").replace("=f", "")
    return add_claim(
        subject=label,
        predicate="price_signal",
        obj=f"{change} (current: {current})",
        claim_type="factual",
        confidence=1.0,
        tags=["price", "intraday", severity],
        source_ref="yfinance",
        excerpt=f"{symbol} moved {change} to {current}",
    )


def write_news_item(source_label: str, title: str, tier: int,
                    tags: list[str] | None = None) -> str | None:
    return add_claim(
        subject="news",
        predicate="headline",
        obj=title[:200],
        claim_type="factual",
        confidence=1.0,
        tags=["news", f"tier_{tier}"] + (tags or []),
        source_ref=source_label,
        excerpt=title[:200],
    )


def write_market_signal(signal_type: str, description: str,
                        confidence: float = 0.8,
                        tags: list[str] | None = None) -> str | None:
    return add_claim(
        subject="market_signal",
        predicate=signal_type,
        obj=description,
        claim_type="inference",
        confidence=confidence,
        tags=["signal"] + (tags or []),
        source_ref="market_watcher/analyzer",
        excerpt=description,
    )


def write_calendar_event(event_name: str, event_date: str,
                         details: str = "") -> str | None:
    return add_claim(
        subject="calendar",
        predicate="upcoming_event",
        obj=f"{event_name} on {event_date}",
        claim_type="factual",
        confidence=1.0,
        tags=["calendar", "scheduled"],
        source_ref="jin10/calendar",
        excerpt=details or f"{event_name} scheduled for {event_date}",
    )


def get_active_narratives() -> list:
    return list_claims(tag="narrative", predicate="active_theme")


def get_recent_signals() -> list:
    return list_claims(tag="signal")


def get_recent_data() -> list:
    return list_claims(tag="data")


def get_recent_news() -> list:
    return list_claims(tag="news")


def get_calendar_events() -> list:
    return list_claims(subject="calendar")
