"""The two allocation rules under comparison.

Only this module differs between the arms; everything else is shared.

FIFO: fill resting orders at a level in arrival_seq order. Size is irrelevant.

Pro-rata, three passes:
  1. floor(demand * size_i / total) to each order, capped at its own size
  2. leftover lots go one at a time to the largest fractional remainders,
     ties by lower arrival_seq
  3. anything still stranded by size caps is swept in arrival_seq order

min_allocation_lots is a participation floor, not a guarantee. An order whose
share is under that many whole lots gets nothing in pass 1 and only competes in
passes 2 and 3. At one lot that is just integer allocation. It is not a rule
that hands every resting order a lot; that would be a different mechanism. The
value arrives from the contract with every call; it used to be a literal here,
which nothing tied to the contract's field.

Both functions are pure in (resting, demand, min_allocation_lots): no simulator
state, no clock, no RNG. That is what makes any outcome difference attributable
to the rule.
"""

from __future__ import annotations

from dataclasses import dataclass


FIFO = "FIFO"
PRO_RATA = "PRO_RATA"
MECHANISMS = (FIFO, PRO_RATA)


@dataclass(frozen=True)
class Resting:
    """A resting order at a single price level."""

    order_id: int
    size: int
    arrival_seq: int


def _allocate_fifo(resting: list[Resting], demand: int) -> dict[int, int]:
    allocation: dict[int, int] = {}
    remaining = demand
    for order in sorted(resting, key=lambda o: o.arrival_seq):
        if remaining <= 0:
            break
        lots = min(order.size, remaining)
        if lots > 0:
            allocation[order.order_id] = lots
            remaining -= lots
    return allocation


def _allocate_pro_rata(resting: list[Resting], demand: int, min_allocation_lots: int) -> dict[int, int]:
    ordered = sorted(resting, key=lambda o: o.arrival_seq)
    total = sum(o.size for o in ordered)
    if total <= 0:
        return {}
    if demand >= total:
        return {o.order_id: o.size for o in ordered if o.size > 0}

    # Pass 1 - proportional floors, capped at resting size.
    #
    # Integer arithmetic throughout. demand * size_i / total in floating point
    # loses precision in proportion to the magnitude of the share, so exactly
    # equal fractional parts compare unequal and the arrival_seq tie-break never
    # gets a chance to run. The remainder is kept as the exact numerator
    # (demand * size_i) mod total instead.
    allocation: dict[int, int] = {}
    remainders: list[tuple[int, int, int]] = []
    for order in ordered:
        numerator = demand * order.size
        floor_lots = min(numerator // total, order.size)
        if floor_lots < min_allocation_lots:
            floor_lots = 0
        allocation[order.order_id] = floor_lots
        remainders.append((numerator % total, order.arrival_seq, order.order_id))

    remaining = demand - sum(allocation.values())

    # Pass 2 - largest-remainder rounding, ties by arrival_seq.
    capacity = {o.order_id: o.size for o in ordered}
    for _, _, order_id in sorted(remainders, key=lambda r: (-r[0], r[1])):
        if remaining <= 0:
            break
        if allocation[order_id] < capacity[order_id]:
            allocation[order_id] += 1
            remaining -= 1

    # Pass 3 - FIFO residual sweep for lots stranded by size caps.
    if remaining > 0:
        for order in ordered:
            if remaining <= 0:
                break
            headroom = capacity[order.order_id] - allocation[order.order_id]
            if headroom > 0:
                lots = min(headroom, remaining)
                allocation[order.order_id] += lots
                remaining -= lots

    return {oid: lots for oid, lots in allocation.items() if lots > 0}


def allocate(mechanism: str, resting: list[Resting], demand: int, min_allocation_lots: int) -> dict[int, int]:
    """Split `demand` lots across `resting` orders at one price level.

    Returns order_id -> lots, skipping zeros. Lots never exceed an order's
    resting size and never sum past demand.
    """
    if min_allocation_lots < 1:
        raise ValueError(f"min_allocation_lots must be a positive lot count, got {min_allocation_lots}")
    if demand <= 0 or not resting:
        return {}
    if mechanism == FIFO:
        return _allocate_fifo(resting, demand)
    if mechanism == PRO_RATA:
        return _allocate_pro_rata(resting, demand, min_allocation_lots)
    raise ValueError(f"unknown mechanism: {mechanism}")
