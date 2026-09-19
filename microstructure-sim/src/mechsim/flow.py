"""Synthetic order flow as a pre-generated intent stream.

The whole stream is drawn up front from (params, seed). Nothing in here looks at
book state, which is the point: both arms consume the same intents and the
identity check is a hash comparison.

Every LIMIT intent carries an immutable intent_id, which is its order id in
whichever arm places it. Cancels are not drawn against a live resting list -
that would pick a different order in each arm once allocation diverges. Instead
each LIMIT gets a lifetime at generation:

    cancel_at = t + Exponential(rate = cancel_rate_per_resting_lot * size)

which applies the declared per-lot intensity literally, and the resulting CANCEL
intent carries the target's intent_id for good. A cancel landing on an order
that is filled, already cancelled or never placed is a counted no-op.

The ten ladder orders are intents 1..10 at t=0 with absolute prices; every other
LIMIT carries a book-relative offset resolved on arrival, so absolute prices may
differ between arms while the intent does not.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .book import BUY, SELL


KIND_LIMIT = "LIMIT"
KIND_MARKET = "MARKET"
KIND_CANCEL = "CANCEL"

BOOK_RELATIVE = 0


@dataclass(frozen=True)
class Intent:
    seq: int
    t_ms: float
    kind: str
    side: int
    size: int
    offset: int
    price: int
    intent_id: int
    target_intent_id: int


def mean_order_size(size_distribution: dict[str, float]) -> float:
    return sum(int(lots) * prob for lots, prob in size_distribution.items())


def event_rates(cfg) -> dict[str, float]:
    """Per-second intensities for the two independently drawn intent kinds.

    Cancels are not drawn independently any more; they are derived per LIMIT, so
    they carry no rate of their own.
    """
    return {
        KIND_LIMIT: cfg.limit_rate_per_level * cfg.levels * 2,
        KIND_MARKET: cfg.market_rate_per_side * 2,
    }


def _ladder_intents(cfg) -> list[tuple[float, int, Intent]]:
    """Intents 1..10: bid level 1, ask level 1, bid level 2, ask level 2, ..."""
    out: list[tuple[float, int, Intent]] = []
    next_id = 1
    for level in range(cfg.levels_per_side):
        for side, prices in ((BUY, cfg.ladder_bid_prices), (SELL, cfg.ladder_ask_prices)):
            out.append(
                (
                    0.0,
                    next_id,
                    Intent(0, 0.0, KIND_LIMIT, side, cfg.lots_per_level, 0, prices[level], next_id, 0),
                )
            )
            next_id += 1
    return out


def generate_stream(cfg, seed: int, n_events: int) -> list[Intent]:
    """Draw the complete pre-mechanism intent stream for one run."""
    rng = np.random.default_rng(seed)
    rates = event_rates(cfg)
    total_rate = rates[KIND_LIMIT] + rates[KIND_MARKET]
    p_limit = rates[KIND_LIMIT] / total_rate

    staged = _ladder_intents(cfg)
    next_id = len(staged) + 1

    # Each LIMIT contributes itself plus one CANCEL, so drawing roughly 60% of
    # the target count leaves margin before truncation.
    n_base = int(n_events * 0.60) + 1000

    gaps = rng.exponential(1.0 / total_rate, size=n_base) * 1000.0
    times = np.cumsum(gaps)
    is_limit = rng.random(n_base) < p_limit
    sides = rng.choice([BUY, SELL], size=n_base)
    offsets = rng.integers(1, cfg.levels + 1, size=n_base)

    lot_values = np.array([int(k) for k in cfg.size_distribution], dtype=int)
    lot_probs = np.array([cfg.size_distribution[k] for k in cfg.size_distribution], dtype=float)
    lot_probs = lot_probs / lot_probs.sum()
    sizes = rng.choice(lot_values, size=n_base, p=lot_probs)

    lifetimes = rng.exponential(1.0, size=n_base)

    # Ladder lifetimes are drawn first so the ladder is cancellable too.
    ladder_lifetimes = rng.exponential(1.0, size=len(staged))
    for (t0, _, intent), draw in zip(list(staged), ladder_lifetimes):
        hazard = cfg.cancel_rate_per_lot * intent.size
        cancel_at = t0 + (draw / hazard) * 1000.0
        staged.append(
            (
                cancel_at,
                intent.intent_id,
                Intent(0, cancel_at, KIND_CANCEL, intent.side, 0, 0, 0, 0, intent.intent_id),
            )
        )

    order = len(staged)
    for i in range(n_base):
        t = float(times[i])
        side = int(sides[i])
        size = int(sizes[i])
        if is_limit[i]:
            intent_id = next_id
            next_id += 1
            staged.append(
                (t, order, Intent(0, t, KIND_LIMIT, side, size, int(offsets[i]), BOOK_RELATIVE, intent_id, 0))
            )
            order += 1
            hazard = cfg.cancel_rate_per_lot * size
            cancel_at = t + (float(lifetimes[i]) / hazard) * 1000.0
            staged.append((cancel_at, order, Intent(0, cancel_at, KIND_CANCEL, side, 0, 0, 0, 0, intent_id)))
            order += 1
        else:
            staged.append((t, order, Intent(0, t, KIND_MARKET, side, size, 0, 0, 0, 0)))
            order += 1

    staged.sort(key=lambda row: (row[0], row[1]))
    if len(staged) < n_events:
        raise RuntimeError(f"intent stream short: {len(staged)} < {n_events}")

    return [
        Intent(
            seq=i,
            t_ms=row[2].t_ms,
            kind=row[2].kind,
            side=row[2].side,
            size=row[2].size,
            offset=row[2].offset,
            price=row[2].price,
            intent_id=row[2].intent_id,
            target_intent_id=row[2].target_intent_id,
        )
        for i, row in enumerate(staged[:n_events])
    ]


def serialize_stream(intents: list[Intent]) -> bytes:
    """Canonical byte serialization used for the identity control."""
    parts = [
        f"{e.seq}|{e.t_ms:.6f}|{e.kind}|{e.side}|{e.size}|{e.offset}|{e.price}|{e.intent_id}|{e.target_intent_id}"
        for e in intents
    ]
    return "\n".join(parts).encode("utf-8")


def stream_digest(intents: list[Intent]) -> str:
    """sha256 of the canonical intent-stream serialization."""
    return hashlib.sha256(serialize_stream(intents)).hexdigest()
