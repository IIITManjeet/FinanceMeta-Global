"""One run: intent stream, latency, and the tracked parent order.

On latency. The stream is the exchange-side arrival process, so background
orders are already at the engine when their intent fires. The tracked agent sees
a trigger at t, so its response lands at t + 2L.

Background latency does nothing here. The background agents are
zero-intelligence and never react, so there is nothing for it to delay. Only the
tracked agent's latency bites. That falls straight out of the frozen participant
assumption and it limits what the sweep can show, so it gets reported rather
than papered over.

The run always executes the full horizon, even once the parent order is done,
because Perold shortfall marks the unfilled remainder at the frozen horizon end
and price impact is measured there too.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass, field, replace

from .book import BUY, OWNER_BACKGROUND, OWNER_TRACKED, SELL, Book
from .contract import Config, frozen_seeds
from .flow import BOOK_RELATIVE, KIND_CANCEL, KIND_LIMIT, KIND_MARKET, Intent, generate_stream, stream_digest
from .mechanisms import FIFO


TRACKED_ID_BASE = 1_000_000_000

# (contract id, sha256 of the contract bytes) pairs whose authorisation receipt
# has been validated in this process. Only reproduce._require_authorisation
# adds to it. allow_frozen_seed=True is therefore inert anywhere a receipt has
# not been checked, tests included, and no scanner has to exempt the one
# legitimate caller. The digest is part of the key because the id is free text
# that any Config can carry; the grant covers the reviewed bytes, not a name.
AUTHORISED_CONTRACTS: set[tuple[str, str, str]] = set()


@dataclass
class RunResult:
    mechanism: str
    seed: int
    latency_ms: int
    cell: str
    stream_sha256: str
    # primary metrics
    fill_probability: float
    implementation_shortfall_bps: float
    spread_at_execution_ticks: float | None
    time_to_first_fill_ms: float | None
    time_to_full_fill_ms: float | None
    queue_measure: float | None
    price_impact_bps: float
    # provenance and degeneracy
    filled_lots: int
    parent_lots: int
    arrival_mid: float
    final_mid: float
    placements: int
    limit_no_ops: int
    cancel_no_ops: int
    market_no_ops: int
    flags: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        """The run record, carrying a digest of itself.

        The data contract requires a record sha256 alongside the intent-stream
        one. The stream digest shows both arms consumed the same flow; this one
        lets a reader check a single run record has not been altered after the
        fact, and gives the byte-identical replay control something to compare
        that does not depend on how the file was serialised.
        """
        record = {
            "mechanism": self.mechanism,
            "seed": self.seed,
            "latency_ms": self.latency_ms,
            "cell": self.cell,
            "stream_sha256": self.stream_sha256,
            "fill_probability": self.fill_probability,
            "implementation_shortfall_bps": self.implementation_shortfall_bps,
            "spread_at_execution_ticks": self.spread_at_execution_ticks,
            "time_to_first_fill_ms": self.time_to_first_fill_ms,
            "time_to_full_fill_ms": self.time_to_full_fill_ms,
            "queue_measure": self.queue_measure,
            "price_impact_bps": self.price_impact_bps,
            "filled_lots": self.filled_lots,
            "parent_lots": self.parent_lots,
            "arrival_mid": self.arrival_mid,
            "final_mid": self.final_mid,
            "placements": self.placements,
            "limit_no_ops": self.limit_no_ops,
            "cancel_no_ops": self.cancel_no_ops,
            "market_no_ops": self.market_no_ops,
            "flags": sorted(self.flags),
        }
        record["record_sha256"] = hashlib.sha256(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return record


def _apply_background(book: Book, intent: Intent, cfg: Config) -> str | None:
    """Apply one intent to the book. Returns a no-op tag, or None if it acted."""
    if intent.kind == KIND_LIMIT:
        if intent.price != BOOK_RELATIVE:
            book.add_limit(intent.side, intent.price, intent.size, OWNER_BACKGROUND, order_id=intent.intent_id)
            return None
        opposite = book.best_ask() if intent.side == BUY else book.best_bid()
        if opposite is None:
            return "limit_no_op"
        price = (
            opposite - intent.offset * cfg.tick
            if intent.side == BUY
            else opposite + intent.offset * cfg.tick
        )
        book.add_limit(intent.side, price, intent.size, OWNER_BACKGROUND, order_id=intent.intent_id)
        return None

    if intent.kind == KIND_MARKET:
        resting_side = SELL if intent.side == BUY else BUY
        if not book.resting_orders(resting_side):
            return "market_no_op"
        book.execute_market(intent.side, intent.size, intent.t_ms)
        return None

    if intent.kind == KIND_CANCEL:
        return None if book.cancel(intent.target_intent_id) else "cancel_no_op"

    raise ValueError(f"unknown intent kind: {intent.kind}")


def _guard_frozen_seed(cfg: Config, seed: int, allow_frozen_seed: bool) -> None:
    """Refuse a frozen seed unless the caller opts in and a receipt has been validated.

    This is a runtime guard rather than a lint rule: the previous protection was
    a static scan of test modules, which an aliased constant, a loop variable or
    a helper call walks straight past. The opt-in flag alone is not enough
    either. A flag is one keyword away from any test, so it is honoured only
    once reproduce._require_authorisation has accepted a receipt for this
    contract, id and bytes both, in this process.
    """
    if seed not in frozen_seeds(cfg):
        return
    if not allow_frozen_seed:
        raise ValueError(
            f"refusing to run frozen seed {seed} without allow_frozen_seed=True: this would "
            "produce an outcome on a development or confirmation seed"
        )
    if (cfg.contract_id, cfg.contract_sha256, cfg.identity()) not in AUTHORISED_CONTRACTS:
        raise ValueError(
            f"refusing to run frozen seed {seed}: allow_frozen_seed=True is honoured only after an "
            f"authorisation receipt for {cfg.contract_id} at {cfg.contract_sha256[:12]} has been validated "
            "in this process"
        )


def run_once(
    cfg: Config,
    mechanism: str,
    seed: int,
    latency_ms: int,
    cell: str = "main",
    size_distribution: dict[str, float] | None = None,
    allow_frozen_seed: bool = False,
) -> RunResult:
    """Run one cell and return its record.

    A development or confirmation seed is refused unless the authorised
    confirmatory run is the caller; see _guard_frozen_seed.

    generate_stream is deliberately not guarded: it emits a deterministic intent
    stream and no outcome, and the published per-seed identity digests are
    produced from it.
    """
    _guard_frozen_seed(cfg, seed, allow_frozen_seed)
    run_cfg = cfg
    if size_distribution is not None:
        run_cfg = replace(cfg, size_distribution=size_distribution)

    intents = generate_stream(run_cfg, seed, run_cfg.total_events)
    digest = stream_digest(intents)

    book = Book(tick=run_cfg.tick, mechanism=mechanism, min_allocation_lots=run_cfg.min_allocation_lots)
    counters = {"limit_no_op": 0, "cancel_no_op": 0, "market_no_op": 0}
    ref_mid = float(run_cfg.initial_mid)

    def bump(tag: str | None) -> None:
        if tag is not None:
            counters[tag] += 1

    for intent in intents[: run_cfg.warm_up_events]:
        bump(_apply_background(book, intent, run_cfg))
        current = book.mid()
        if current is not None:
            ref_mid = current

    measured = intents[run_cfg.warm_up_events :]
    arrival_carried = book.mid() is None
    arrival_mid = ref_mid
    t0 = measured[0].t_ms if measured else 0.0

    remaining = run_cfg.parent_quantity
    filled_lots = 0
    executions: list[tuple[int, int, float, int]] = []  # price, lots, t_ms, spread
    queue_samples: list[float] = []
    placements = 0
    tracked_id: int | None = None
    next_tracked_id = TRACKED_ID_BASE
    pending_at: float | None = None
    delay = 2.0 * latency_ms

    def schedule(now: float) -> None:
        nonlocal pending_at
        if pending_at is None and remaining > 0:
            pending_at = now + delay

    def target_display() -> int:
        return min(run_cfg.display_lots, remaining)

    def needs_action() -> bool:
        """True when the tracked order is absent, mispriced, or under-displayed."""
        if remaining <= 0:
            return False
        if tracked_id is None or not book.is_live(tracked_id):
            return True
        return book.price_of(tracked_id) != book.best_bid() or book.size_of(tracked_id) < target_display()

    def act(now: float) -> None:
        nonlocal tracked_id, placements, pending_at, next_tracked_id
        pending_at = None
        best_bid = book.best_bid()
        if best_bid is None or remaining <= 0:
            return
        if tracked_id is not None and book.is_live(tracked_id):
            if book.price_of(tracked_id) == best_bid and book.size_of(tracked_id) >= target_display():
                return
            # Topping up displayed quantity loses time priority on a real
            # exchange, so the order is cancelled and replaced rather than
            # silently grown in place.
            book.cancel(tracked_id)
            tracked_id = None
        next_tracked_id += 1
        tracked_id = next_tracked_id
        book.add_limit(BUY, best_bid, target_display(), OWNER_TRACKED, order_id=tracked_id)
        placements += 1
        queue_samples.append(
            float(book.volume_ahead(tracked_id))
            if mechanism == FIFO
            else float(book.size_share(tracked_id))
        )

    schedule(t0)

    for intent in measured:
        t = intent.t_ms
        if pending_at is not None and pending_at <= t:
            act(pending_at)

        if intent.kind == KIND_MARKET:
            resting_side = SELL if intent.side == BUY else BUY
            if book.resting_orders(resting_side):
                for fill in book.execute_market(intent.side, intent.size, t):
                    if fill.owner == OWNER_TRACKED:
                        filled_lots += fill.lots
                        remaining -= fill.lots
                        executions.append((fill.price, fill.lots, fill.t_ms, fill.spread_ticks))
                if tracked_id is not None and not book.is_live(tracked_id):
                    tracked_id = None
                if needs_action():
                    schedule(t)
            else:
                counters["market_no_op"] += 1
        else:
            before = book.best_bid()
            bump(_apply_background(book, intent, run_cfg))
            if book.best_bid() != before and needs_action():
                schedule(t)

        current = book.mid()
        if current is not None:
            ref_mid = current

    horizon_carried = book.mid() is None
    final_mid = ref_mid

    parent = run_cfg.parent_quantity
    executed_value = sum(price * lots for price, lots, _, _ in executions)
    unfilled = parent - filled_lots
    shortfall = 1e4 * (executed_value + unfilled * final_mid - parent * arrival_mid) / (parent * arrival_mid)
    impact = 1e4 * (final_mid - arrival_mid) / arrival_mid

    total_lots = sum(lots for _, lots, _, _ in executions)
    if total_lots > 0:
        spread_exec = sum(sp * lots for _, lots, _, sp in executions) / total_lots
        first_fill = min(t for _, _, t, _ in executions) - t0
    else:
        spread_exec = None
        first_fill = None
    full_fill = (max(t for _, _, t, _ in executions) - t0) if remaining <= 0 and executions else None

    flags: list[str] = []
    if filled_lots == 0:
        flags.append("no_fill")
    if remaining > 0:
        flags.append("parent_unfilled")
    if placements == 0:
        flags.append("never_quoted")
    if arrival_carried:
        flags.append("arrival_mid_carried_forward")
    if horizon_carried:
        flags.append("horizon_mid_carried_forward")
    for tag, count in counters.items():
        if count:
            flags.append(f"{tag}s")

    return RunResult(
        mechanism=mechanism,
        seed=seed,
        latency_ms=latency_ms,
        cell=cell,
        stream_sha256=digest,
        fill_probability=filled_lots / parent,
        implementation_shortfall_bps=shortfall,
        spread_at_execution_ticks=spread_exec,
        time_to_first_fill_ms=first_fill,
        time_to_full_fill_ms=full_fill,
        queue_measure=(sum(queue_samples) / len(queue_samples)) if queue_samples else None,
        price_impact_bps=impact,
        filled_lots=filled_lots,
        parent_lots=parent,
        arrival_mid=arrival_mid,
        final_mid=final_mid,
        placements=placements,
        limit_no_ops=counters["limit_no_op"],
        cancel_no_ops=counters["cancel_no_op"],
        market_no_ops=counters["market_no_op"],
        flags=flags,
    )
