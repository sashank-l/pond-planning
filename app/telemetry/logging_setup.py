"""OpenTelemetry structured logging configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from opentelemetry import trace


class OTelLogFormatter(logging.Formatter):
    """Custom logging formatter injecting active OpenTelemetry trace and span IDs."""

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None

        if ctx and ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
            record.trace_sampled = ctx.trace_flags.sampled
        else:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16
            record.trace_sampled = False

        return super().format(record)


def init_logging(log_level: int = logging.INFO) -> None:
    """Initialize OpenTelemetry-aware structured logging."""
    logs_dir = Path("/home/student/pond_panning/logs")
    if not logs_dir.exists():
        logs_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "telemetry.log"

    formatter = OTelLogFormatter(
        fmt="[%(asctime)s] [%(levelname)s] [trace_id=%(trace_id)s span_id=%(span_id)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if re-initialized
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # 1. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # 2. File Handler (logs/telemetry.log)
    try:
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    except Exception as exc:
        print(f"Failed to create telemetry log file: {exc}", file=sys.stderr)

    logging.getLogger("uvicorn.access").handlers = [console_handler]
    logging.getLogger("uvicorn.error").handlers = [console_handler]
