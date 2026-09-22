"""Limit order book mechanics, held constant across mechanisms."""

from __future__ import annotations

import pytest

from mechsim.book import BUY, OWNER_BACKGROUND, OWNER_TRACKED, SELL, Book


def empty(mechanism: str = "FIFO") -> Book:
    return Book(tick=1, mechanism=mechanism, min_allocation_lots=1)


def fresh(mechanism: str = "FIFO") -> Book:
    book = empty(mechanism)
    for level in range(1, 4):
        book.add_limit(BUY, 100 - level, 10, OWNER_BACKGROUND)
        book.add_limit(SELL, 100 + level, 10, OWNER_BACKGROUND)
    return book


def test_best_prices_and_spread() -> None:
    book = fresh()
    assert book.best_bid() == 99
    assert book.best_ask() == 101
    assert book.mid() == 100.0
    assert book.spread_ticks() == 2


def test_empty_book_reports_none() -> None:
    book = empty()
    assert book.best_bid() is None
    assert book.best_ask() is None
    assert book.mid() is None
    assert book.spread_ticks() is None


def test_cancel_removes_order_and_empties_level() -> None:
    book = empty()
    oid = book.add_limit(BUY, 99, 5, OWNER_BACKGROUND)
    assert book.is_live(oid)
    assert book.cancel(oid) is True
    assert not book.is_live(oid)
    assert book.best_bid() is None
    assert book.cancel(oid) is False


def test_market_order_consumes_best_level_first() -> None:
    book = fresh()
    fills = book.execute_market(BUY, 10, t_ms=0.0)
    assert all(f.price == 101 for f in fills)
    assert sum(f.lots for f in fills) == 10
    assert book.best_ask() == 102


def test_market_order_walks_multiple_levels() -> None:
    book = fresh()
    fills = book.execute_market(BUY, 25, t_ms=0.0)
    assert sum(f.lots for f in fills) == 25
    assert {f.price for f in fills} == {101, 102, 103}


def test_market_order_against_empty_side_fills_nothing() -> None:
    book = empty()
    book.add_limit(BUY, 99, 10, OWNER_BACKGROUND)
    assert book.execute_market(BUY, 10, t_ms=0.0) == []


def test_oversized_market_order_drains_the_side() -> None:
    book = fresh()
    fills = book.execute_market(BUY, 1000, t_ms=0.0)
    assert sum(f.lots for f in fills) == 30
    assert book.best_ask() is None


def test_volume_ahead_counts_only_earlier_arrivals_at_same_price() -> None:
    book = empty()
    first = book.add_limit(BUY, 99, 7, OWNER_BACKGROUND)
    second = book.add_limit(BUY, 99, 3, OWNER_TRACKED)
    book.add_limit(BUY, 98, 50, OWNER_BACKGROUND)
    assert book.volume_ahead(first) == 0
    assert book.volume_ahead(second) == 7


def test_size_share_is_fraction_of_level_depth() -> None:
    book = empty()
    book.add_limit(BUY, 99, 30, OWNER_BACKGROUND)
    tracked = book.add_limit(BUY, 99, 10, OWNER_TRACKED)
    assert book.size_share(tracked) == pytest.approx(0.25)


def test_queue_measures_are_zero_for_unknown_order() -> None:
    book = fresh()
    assert book.volume_ahead(999999) == 0
    assert book.size_share(999999) == 0.0


def test_resting_orders_filter_by_owner() -> None:
    book = empty()
    book.add_limit(BUY, 99, 5, OWNER_BACKGROUND)
    book.add_limit(BUY, 99, 5, OWNER_TRACKED)
    assert len(book.resting_orders(BUY)) == 2
    assert len(book.resting_orders(BUY, owner=OWNER_TRACKED)) == 1


def test_non_positive_limit_size_is_rejected() -> None:
    book = empty()
    with pytest.raises(ValueError):
        book.add_limit(BUY, 99, 0, OWNER_BACKGROUND)


def test_fills_record_spread_at_execution() -> None:
    book = fresh()
    fills = book.execute_market(BUY, 5, t_ms=12.5)
    assert fills[0].spread_ticks == 2
    assert fills[0].t_ms == 12.5
