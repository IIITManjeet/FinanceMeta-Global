"""Limit order book. Shared by both arms.

The book only knows the mechanism as a string it hands to mechanisms.allocate.
Levels, order lifecycle, cancels and market sweeps are the same either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .mechanisms import Resting, allocate


BUY = 1
SELL = -1

OWNER_BACKGROUND = "BG"
OWNER_TRACKED = "TRK"


@dataclass
class Order:
    order_id: int
    side: int
    price: int
    size: int
    arrival_seq: int
    owner: str


@dataclass
class Fill:
    order_id: int
    owner: str
    price: int
    lots: int
    aggressor_side: int
    t_ms: float
    spread_ticks: int


@dataclass
class Book:
    tick: int
    mechanism: str
    min_allocation_lots: int
    _bids: dict[int, list[Order]] = field(default_factory=dict)
    _asks: dict[int, list[Order]] = field(default_factory=dict)
    _index: dict[int, Order] = field(default_factory=dict)
    _next_id: int = 0
    _next_seq: int = 0

    # state

    def _side_map(self, side: int) -> dict[int, list[Order]]:
        return self._bids if side == BUY else self._asks

    def best_bid(self) -> int | None:
        live = [p for p, q in self._bids.items() if q]
        return max(live) if live else None

    def best_ask(self) -> int | None:
        live = [p for p, q in self._asks.items() if q]
        return min(live) if live else None

    def mid(self) -> float | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0

    def spread_ticks(self) -> int | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return (ask - bid) // self.tick

    def depth_at(self, side: int, price: int) -> int:
        return sum(o.size for o in self._side_map(side).get(price, []))

    def volume_ahead(self, order_id: int) -> int:
        """Lots resting ahead of order_id at its own price."""
        order = self._index.get(order_id)
        if order is None:
            return 0
        queue = self._side_map(order.side).get(order.price, [])
        return sum(o.size for o in queue if o.arrival_seq < order.arrival_seq)

    def size_share(self, order_id: int) -> float:
        """Share of resting size at the order's own price level."""
        order = self._index.get(order_id)
        if order is None:
            return 0.0
        total = self.depth_at(order.side, order.price)
        return (order.size / total) if total > 0 else 0.0

    def is_live(self, order_id: int) -> bool:
        return order_id in self._index

    def price_of(self, order_id: int) -> int | None:
        order = self._index.get(order_id)
        return order.price if order is not None else None

    def size_of(self, order_id: int) -> int:
        order = self._index.get(order_id)
        return order.size if order is not None else 0

    # lifecycle

    def add_limit(self, side: int, price: int, size: int, owner: str, order_id: int | None = None) -> int:
        """Place a resting order. `order_id` lets a background order keep its intent_id."""
        if size <= 0:
            raise ValueError("limit size must be positive")
        if order_id is None:
            self._next_id += 1
            order_id = self._next_id
        self._next_seq += 1
        order = Order(order_id, side, price, size, self._next_seq, owner)
        self._side_map(side).setdefault(price, []).append(order)
        self._index[order.order_id] = order
        return order.order_id

    def cancel(self, order_id: int) -> bool:
        order = self._index.pop(order_id, None)
        if order is None:
            return False
        queue = self._side_map(order.side).get(order.price, [])
        for i, resting in enumerate(queue):
            if resting.order_id == order_id:
                queue.pop(i)
                break
        if not queue:
            self._side_map(order.side).pop(order.price, None)
        return True

    def resting_orders(self, side: int, owner: str | None = None) -> list[Order]:
        out: list[Order] = []
        for queue in self._side_map(side).values():
            for order in queue:
                if owner is None or order.owner == owner:
                    out.append(order)
        out.sort(key=lambda o: o.arrival_seq)
        return out

    # matching

    def execute_market(self, side: int, size: int, t_ms: float) -> list[Fill]:
        """Aggressive order of `size` lots on `side`.

        side is the aggressor: BUY eats asks, SELL eats bids. Levels go
        best-first; inside a level the mechanism decides who fills.
        """
        fills: list[Fill] = []
        remaining = size
        resting_side = SELL if side == BUY else BUY
        book_side = self._side_map(resting_side)

        while remaining > 0:
            live = [p for p, q in book_side.items() if q]
            if not live:
                break
            price = min(live) if resting_side == SELL else max(live)
            queue = book_side[price]
            spread = self.spread_ticks()

            resting = [Resting(o.order_id, o.size, o.arrival_seq) for o in queue]
            allocation = allocate(self.mechanism, resting, remaining, self.min_allocation_lots)
            if not allocation:
                break

            for order_id, lots in allocation.items():
                order = self._index[order_id]
                order.size -= lots
                remaining -= lots
                fills.append(
                    Fill(
                        order_id=order_id,
                        owner=order.owner,
                        price=price,
                        lots=lots,
                        aggressor_side=side,
                        t_ms=t_ms,
                        spread_ticks=spread if spread is not None else 0,
                    )
                )

            for order in list(queue):
                if order.size <= 0:
                    self._index.pop(order.order_id, None)
                    queue.remove(order)
            if not queue:
                book_side.pop(price, None)

        return fills
