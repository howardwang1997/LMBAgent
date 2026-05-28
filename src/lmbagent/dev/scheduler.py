"""Scheduler for daily midnight git commit & push of workspace changes.

Uses the `schedule` library with a background daemon thread.
At midnight (00:00), it commits all workspace/ changes and pushes
to the current branch on GitHub.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from lmbagent.dev.sandbox import SANDBOX_ROOT

logger = logging.getLogger(__name__)

REPO_ROOT = SANDBOX_ROOT.parent

_scheduler_thread: threading.Thread | None = None
_started = False


def _get_current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or "main"
    except Exception:
        return "main"


def auto_commit_push() -> str:
    """Stage, commit, and push workspace changes.

    Returns a status message string.
    """
    if not SANDBOX_ROOT.exists():
        return "workspace/ does not exist, nothing to commit"

    try:
        subprocess.run(
            ["git", "add", "workspace/"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )

        diff_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )

        if diff_result.returncode == 0:
            return "No changes to commit"

        now = datetime.now()
        msg = f"auto(dev): workspace update {now:%Y-%m-%d %H:%M}"

        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )

        branch = _get_current_branch()
        subprocess.run(
            ["git", "push", "origin", branch],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )

        logger.info("Auto-commit push succeeded: %s", msg)
        return f"Committed and pushed: {msg}"

    except subprocess.TimeoutExpired:
        return "Git operation timed out"
    except Exception as e:
        logger.error("Auto-commit push failed: %s", e)
        return f"Git error: {e}"


def manual_commit_push() -> str:
    """Manually trigger a commit & push (for UI button)."""
    return auto_commit_push()


def start_scheduler() -> None:
    """Start the background scheduler daemon.

    Safe to call multiple times — only starts once.
    """
    global _scheduler_thread, _started

    if _started:
        return
    _started = True

    try:
        import schedule
    except ImportError:
        logger.warning("schedule not installed, auto-commit disabled")
        return

    schedule.every().day.at("00:00").do(auto_commit_push)

    def _run():
        import time
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                logger.error("Scheduler error: %s", e)
            time.sleep(60)

    _scheduler_thread = threading.Thread(target=_run, daemon=True, name="dev-scheduler")
    _scheduler_thread.start()
    logger.info("Dev workspace scheduler started (auto-commit at 00:00)")
