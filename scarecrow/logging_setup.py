"""Shared structured logger for scarecrow-drone Python code.

Format: `[<iso8601-utc> LEVEL component] key=value key=value ...`

All logs go to stdout AND to a per-run file under `output/logs/`.

Usage:
    from scarecrow.logging_setup import get_logger, log_event
    log = get_logger("flight.takeoff", run_id="abc123")
    log.info("event=takeoff_request altitude=2.5")
    log_event(log, "arm_ack", result="ACCEPTED", elapsed_ms=289)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "output" / "logs"


class _UtcIsoFormatter(logging.Formatter):
    """Format records as `[<iso8601-utc> LEVEL component] msg`."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z"
        return f"[{ts} {record.levelname} {record.name}] {record.getMessage()}"


_configured: dict[str, logging.Logger] = {}
_run_log_file: Path | None = None


def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _open_run_log(prefix: str, run_id: str | None) -> Path:
    """Open a per-run log file. Reused across get_logger() calls in the same process."""
    global _run_log_file
    if _run_log_file is not None:
        return _run_log_file
    _ensure_log_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"_{run_id}" if run_id else ""
    _run_log_file = LOG_DIR / f"{prefix}_{stamp}{suffix}.log"
    return _run_log_file


def get_logger(name: str, *, run_id: str | None = None, prefix: str = "flight") -> logging.Logger:
    """Get a logger. First call in process opens the per-run log file."""
    if name in _configured:
        return _configured[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = _UtcIsoFormatter()
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    log_file = _open_run_log(prefix, run_id)
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file)
               for h in logger.handlers):
        fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    _configured[name] = logger
    return logger


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    """Emit a key=value structured line. Bool/None/numeric are stringified naturally;
    strings with spaces get quoted."""
    parts = [f"event={event}"]
    for k, v in fields.items():
        if v is None:
            parts.append(f"{k}=null")
        elif isinstance(v, bool):
            parts.append(f"{k}={'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            parts.append(f"{k}={v}")
        else:
            s = str(v)
            if " " in s or "\t" in s or '"' in s:
                s_escaped = s.replace('\\', '\\\\').replace('"', '\\"')
                parts.append(f'{k}="{s_escaped}"')
            else:
                parts.append(f"{k}={s}")
    logger.log(level, " ".join(parts))


class Timer:
    """Context manager that emits begin/end events with elapsed_ms."""

    def __init__(self, logger: logging.Logger, event_name: str, **fields):
        self.logger = logger
        self.event_name = event_name
        self.fields = fields
        self.start = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        log_event(self.logger, f"{self.event_name}_begin", **self.fields)
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed_ms = int((time.monotonic() - self.start) * 1000)
        if exc_type is None:
            log_event(self.logger, f"{self.event_name}_end", elapsed_ms=elapsed_ms, **self.fields)
        else:
            log_event(self.logger, f"{self.event_name}_fail",
                      level=logging.ERROR, elapsed_ms=elapsed_ms,
                      error_type=exc_type.__name__, error=str(exc), **self.fields)
        return False


def log_run_file_path() -> Path | None:
    """Return path of the per-run log file (None if no logger has been opened)."""
    return _run_log_file
