import logging
from typing import Any


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def log_event(logger: logging.Logger, level: str, event: str, **fields: Any) -> None:
    parts: list[str] = []
    for key in sorted(fields):
        value = fields[key]
        if value is None:
            continue
        parts.append(f"{key}={value}")
    msg = f"{event} {' '.join(parts)}".strip()
    if level == "exception":
        logger.exception(msg)
        return
    getattr(logger, level, logger.info)(msg)
