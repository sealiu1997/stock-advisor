"""B5 Layer 2: Agent-based inference refinement.

After the rule engine (selector.py) picks candidate inferences,
this module provides a structured prompt + result parser for an
LLM agent to refine/rank them based on portfolio context.

Usage:
  1. Automated: daemon calls `schedule_agent_refinement()` daily
  2. Manual: `python -m market_watcher refine [--dry-run]`
  3. Agent skill: hermes or other agent calls `refine_inferences()` directly

The agent receives:
  - Today's rule-selected inferences (from selector Layer 1)
  - Current portfolio context
  - Active PKS narratives for continuity

It returns:
  - Ranked inferences with adjusted confidence
  - Optional synthesis/summary
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import pks
from .material import MaterialStore

logger = logging.getLogger("market_watcher.agent_refine")


def build_refinement_prompt(
    inferences: list[dict],
    portfolio_context: str = "",
    active_narratives: list[str] | None = None,
) -> str:
    """Build a structured prompt for agent inference refinement."""
    parts = [
        "你是一个投资研究分析师。请根据以下信息，对候选推断进行精选和排序。",
        "",
        "## 候选推断（规则引擎初筛结果）",
    ]

    for i, inf in enumerate(inferences, 1):
        parts.append(f"\n### 推断 {i}")
        parts.append(f"- 主题: {inf.get('object', '')}")
        parts.append(f"- 置信度: {inf.get('confidence', 0)}")
        parts.append(f"- 驱动类型: {inf.get('metadata', {}).get('driver_type', 'unknown')}")
        parts.append(f"- 证据数: {inf.get('metadata', {}).get('evidence_count', 0)}")
        if inf.get("excerpt"):
            parts.append(f"- 摘要: {inf['excerpt'][:200]}")

    if portfolio_context:
        parts.append("\n## 当前持仓/关注")
        parts.append(portfolio_context)

    if active_narratives:
        parts.append("\n## 活跃叙事（PKS 现有）")
        for n in active_narratives:
            parts.append(f"- {n}")

    parts.extend([
        "",
        "## 任务",
        "1. 评估每条推断的可靠性和投资相关性",
        "2. 过滤掉低质量/不相关的推断",
        "3. 调整置信度（0.5-0.95）",
        "4. 按重要性排序",
        "",
        "## 输出格式（JSON）",
        '{"refined": [{"index": 1, "keep": true, "confidence": 0.85, "reason": "..."}], "synthesis": "一句话总结今日市场主题"}',
    ])

    return "\n".join(parts)


def parse_refinement_result(raw: str) -> dict | None:
    """Parse agent's JSON response."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _get_portfolio_summary() -> str:
    """Build a concise portfolio summary for the agent."""
    lines = []
    for name, path in [("持仓", "config/portfolio.json"), ("关注", "config/watchlist.json")]:
        p = Path(path)
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        for market, items in data.items():
            symbols = [f"{item.get('name', '')}({item.get('symbol', '')})" for item in items[:10]]
            if symbols:
                lines.append(f"{name} {market}: {', '.join(symbols)}")
    return "\n".join(lines)


def refine_inferences(
    inferences: list[dict],
    agent_call: Any = None,
) -> list[dict]:
    """Run Layer 2 agent refinement on rule-selected inferences.

    Args:
        inferences: Rule-engine selected inferences from selector.py
        agent_call: Callable that takes a prompt string and returns agent response string.
                    If None, returns inferences unchanged (agent not available).
    """
    if not inferences:
        return []

    if agent_call is None:
        logger.info("No agent available, returning rule-selected inferences as-is")
        return inferences

    active = pks.get_active_narratives()
    narrative_texts = []
    for n in active:
        obj = n.object if hasattr(n, "object") else n.get("object", "")
        narrative_texts.append(obj[:100])

    prompt = build_refinement_prompt(
        inferences,
        portfolio_context=_get_portfolio_summary(),
        active_narratives=narrative_texts,
    )

    try:
        response = agent_call(prompt)
        result = parse_refinement_result(response)
    except Exception as e:
        logger.warning(f"Agent refinement failed: {e}")
        return inferences

    if not result or "refined" not in result:
        logger.warning("Agent returned invalid result, using rule-selected")
        return inferences

    refined = []
    for item in result["refined"]:
        idx = item.get("index", 0) - 1
        if 0 <= idx < len(inferences) and item.get("keep", True):
            inf = inferences[idx].copy()
            if "confidence" in item:
                inf["confidence"] = max(0.5, min(0.95, item["confidence"]))
            if "reason" in item:
                inf["metadata"] = inf.get("metadata", {})
                inf["metadata"]["agent_reason"] = item["reason"]
            refined.append(inf)

    if result.get("synthesis"):
        logger.info(f"Agent synthesis: {result['synthesis']}")

    logger.info(f"Agent refined: {len(inferences)} → {len(refined)} inferences")
    return refined


def run_agent_refinement(
    store: MaterialStore | None = None,
    agent_call: Any = None,
    day: date | None = None,
) -> dict:
    """Full agent refinement pipeline: load today's selections → refine → update PKS."""
    store = store or MaterialStore()
    day = day or date.today()

    raw_inferences = store.load_selection("selected_inferences.json", day)
    if not raw_inferences:
        return {"status": "no_inferences", "date": day.isoformat()}

    refined = refine_inferences(raw_inferences, agent_call)

    store.save_selection("refined_inferences.json", refined, day)

    return {
        "status": "ok",
        "date": day.isoformat(),
        "input_count": len(raw_inferences),
        "output_count": len(refined),
    }
