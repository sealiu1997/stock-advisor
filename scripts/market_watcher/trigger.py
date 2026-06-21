"""Hermes trigger — wake Hermes to analyze and notify user via Feishu.

Flow: market_watcher detects event → writes to PKS → invokes Hermes →
      Hermes reads PKS, analyzes, composes message → sends via Feishu.

Watcher only "wakes" Hermes with a brief context. Hermes owns the analysis
and delivery. This keeps watcher as a pure data pipeline.
"""

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("market_watcher.trigger")


def notify_agent(events: list[dict], config: dict) -> bool:
    """Wake Hermes to handle high-impact market events.
    Returns True if Hermes was invoked successfully."""
    if not events:
        return False

    critical = [e for e in events if e.get("level") == "critical"]
    high = [e for e in events if e.get("level") == "high"]

    headline_items = []
    for e in (critical + high)[:5]:
        headline_items.append(f"- [{e['level'].upper()}] {e.get('description', '')}")
    headlines = "\n".join(headline_items)

    prompt = (
        f"[Market Watcher 自动触发] 检测到 {len(critical)} 个 CRITICAL、"
        f"{len(high)} 个 HIGH 级别市场事件。\n\n"
        f"摘要（前5条）:\n{headlines}\n\n"
        f"完整数据已写入 PKS market-context。"
        f"请读取 PKS 分析这些事件的影响，结合持仓情况，"
        f"通过飞书通知用户。如果是重大事件，给出简要的操作建议。"
    )

    notification_cfg = config.get("notification", {})
    hermes_cfg = notification_cfg.get("hermes", {})

    success = _invoke_hermes(prompt, hermes_cfg)

    if not success:
        _fallback_stdout(events)

    return success


def _invoke_hermes(prompt: str, hermes_cfg: dict) -> bool:
    """Invoke Hermes via CLI command.

    hermes_cfg expects:
      hermes_dir: Hermes installation directory (required)
      hermes_cmd: command template (optional, default: "hermes run")
      timeout:    seconds to wait (optional, default: 120)
    """
    hermes_dir = hermes_cfg.get("hermes_dir", "")
    if not hermes_dir:
        logger.warning(
            "Hermes not configured. Set notification.hermes.hermes_dir "
            "in watcher.json. Falling back to stdout."
        )
        return False

    hermes_path = Path(hermes_dir).expanduser()
    if not hermes_path.exists():
        logger.warning(f"Hermes directory not found: {hermes_path}")
        return False

    cmd_template = hermes_cfg.get("hermes_cmd", "hermes run")
    timeout = hermes_cfg.get("timeout", 120)

    try:
        result = subprocess.run(
            [*cmd_template.split(), "--prompt", prompt],
            cwd=str(hermes_path),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            logger.info("Hermes invoked successfully")
            return True
        else:
            logger.warning(
                f"Hermes exited with code {result.returncode}: "
                f"{result.stderr[:200] if result.stderr else '(no stderr)'}"
            )
            return False
    except FileNotFoundError:
        logger.warning(
            f"Hermes command not found: {cmd_template}. "
            f"Check notification.hermes.hermes_cmd in watcher.json."
        )
        return False
    except subprocess.TimeoutExpired:
        logger.warning(f"Hermes invocation timed out ({timeout}s)")
        return False
    except Exception as e:
        logger.error(f"Failed to invoke Hermes: {e}")
        return False


def _fallback_stdout(events: list[dict]) -> None:
    """Fallback: print to stdout (captured by launchd logging)."""
    lines = ["", "=" * 60, "Market Watcher Alert (Hermes unavailable, stdout fallback)"]
    for e in events:
        level = e.get("level", "?").upper()
        etype = e.get("type", "?")
        desc = e.get("description", "")
        lines.append(f"[{level}] ({etype}) {desc}")
    lines.extend(["=" * 60, ""])
    print("\n".join(lines))


def format_event(event_type: str, event: dict, level: str) -> dict:
    """Format a raw event into a notification-ready structure."""
    descriptions = {
        "fred": lambda e: (
            f"FRED {e.get('label', e.get('series_id', '?'))}: "
            f"{e.get('value')} ({e.get('date')})"
        ),
        "jin10_flash": lambda e: (
            e.get("content") or e.get("title", "")
        )[:100],
        "rss": lambda e: (
            f"[{e.get('source_label', '?')}] {e.get('title', '')}"
        ),
        "price": lambda e: (
            f"{e.get('label', e.get('symbol', '?'))}: {e.get('change')}"
        ),
    }
    formatter = descriptions.get(event_type, lambda e: str(e)[:100])
    return {
        "type": event_type,
        "level": level,
        "description": formatter(event),
        "raw": event,
    }
