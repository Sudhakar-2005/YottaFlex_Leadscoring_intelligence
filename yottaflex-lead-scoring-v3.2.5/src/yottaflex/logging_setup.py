from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    root = logging.getLogger("yottaflex")
    if root.handlers:
        return root
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)
    root.propagate = False
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"yottaflex.{name}")
