"""Deterministic limit-order-book simulator for a frozen two-mechanism comparison.

Author: Manjeet Pathak. Synthetic simulation only - see the frozen contract in
evaluation/microstructure-mechanism-2026-09/ for the claim boundary.
"""

from .book import Book, Fill, Order
from .contract import Config, load_config
from .mechanisms import FIFO, MECHANISMS, PRO_RATA, Resting, allocate
from .sim import RunResult, run_once

__all__ = [
    "Book",
    "Config",
    "FIFO",
    "Fill",
    "MECHANISMS",
    "Order",
    "PRO_RATA",
    "Resting",
    "RunResult",
    "allocate",
    "load_config",
    "run_once",
]
