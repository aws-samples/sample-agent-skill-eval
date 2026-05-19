"""Logging configuration for skill-eval CLI."""

from __future__ import annotations

import logging
import sys


LOG = logging.getLogger("skill_eval")


def configure_logging(
    debug: bool = False,
    debug_log: str | None = None,
) -> None:
    """Configure logging based on CLI flags.

    Args:
        debug: If True, emit DEBUG logs to stderr.
        debug_log: If set, write DEBUG logs to this file path.
    """
    # If neither flag is set, keep logging quiet (WARNING only)
    if not debug and not debug_log:
        logging.basicConfig(level=logging.WARNING, force=True)
        return

    handlers: list[logging.Handler] = []

    if debug:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.DEBUG)
        stderr_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        handlers.append(stderr_handler)

    if debug_log:
        file_handler = logging.FileHandler(debug_log, mode="w")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        ))
        handlers.append(file_handler)

    logging.basicConfig(level=logging.DEBUG, handlers=handlers, force=True)
