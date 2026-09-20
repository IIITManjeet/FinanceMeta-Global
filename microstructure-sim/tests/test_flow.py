"""Intent-stream schema: immutable ids, derived cancels, hash scope."""

from __future__ import annotations

import dataclasses

import pytest


# Sentinel seeds only - never a frozen development or confirmation seed.
SENTINEL = (900_000_201, 900_000_202, 900_000_203, 900_000_204, 900_000_205)

from mechsim.contract import load_config
from mechsim.flow import (
    BOOK_RELATIVE,
    KIND_CANCEL,
    KIND_LIMIT,
    KIND_MARKET,
    generate_stream,
    serialize_stream,
    stream_digest,
)
from mechsim.sim import TRACKED_ID_BASE


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def stream(cfg):
    return generate_stream(cfg, seed=SENTINEL[0], n_events=4000)


def test_every_cancel_names_a_limit_that_exists(stream) -> None:
    """The point of the schema: no arm ever picks a cancel target itself."""
    limit_ids = {i.intent_id for i in stream if i.kind == KIND_LIMIT}
    cancels = [i for i in stream if i.kind == KIND_CANCEL]
    assert cancels, "stream should contain cancels"
    for cancel in cancels:
        assert cancel.target_intent_id in limit_ids


def test_limit_intent_ids_are_unique(stream) -> None:
    ids = [i.intent_id for i in stream if i.kind == KIND_LIMIT]
    assert len(ids) == len(set(ids))


def test_cancels_never_target_the_tracked_namespace(stream) -> None:
    for cancel in (i for i in stream if i.kind == KIND_CANCEL):
        assert cancel.target_intent_id < TRACKED_ID_BASE


def test_ladder_is_the_first_ten_intents_at_absolute_prices(cfg, stream) -> None:
    ladder = stream[:10]
    assert all(i.kind == KIND_LIMIT for i in ladder)
    assert all(i.t_ms == 0.0 for i in ladder)
    assert all(i.price != BOOK_RELATIVE for i in ladder)
    assert {i.intent_id for i in ladder} == set(range(1, 11))
    prices = {i.price for i in ladder}
    assert prices == set(cfg.ladder_bid_prices) | set(cfg.ladder_ask_prices)


def test_non_ladder_limits_are_book_relative(stream) -> None:
    later = [i for i in stream[10:] if i.kind == KIND_LIMIT]
    assert later, "expected limit intents after the ladder"
    assert all(i.price == BOOK_RELATIVE for i in later)
    assert all(1 <= i.offset <= 5 for i in later)


def test_stream_is_time_ordered(stream) -> None:
    times = [i.t_ms for i in stream]
    assert times == sorted(times)


def test_stream_is_deterministic_for_a_seed(cfg) -> None:
    a = stream_digest(generate_stream(cfg, SENTINEL[2], 2000))
    b = stream_digest(generate_stream(cfg, SENTINEL[2], 2000))
    assert a == b


def test_different_seeds_give_different_streams(cfg) -> None:
    digests = {stream_digest(generate_stream(cfg, s, 2000)) for s in SENTINEL[:5]}
    assert len(digests) == 5


def test_digest_covers_the_cancel_target(cfg, stream) -> None:
    """Changing which order a cancel names must change the hash."""
    mutated = list(stream)
    idx = next(i for i, e in enumerate(mutated) if e.kind == KIND_CANCEL)
    mutated[idx] = dataclasses.replace(mutated[idx], target_intent_id=mutated[idx].target_intent_id + 1)
    assert stream_digest(mutated) != stream_digest(stream)


def test_digest_covers_intent_ids(cfg, stream) -> None:
    mutated = list(stream)
    idx = next(i for i, e in enumerate(mutated) if e.kind == KIND_LIMIT and e.intent_id > 10)
    mutated[idx] = dataclasses.replace(mutated[idx], intent_id=999999)
    assert stream_digest(mutated) != stream_digest(stream)


def test_serialization_has_one_line_per_intent(stream) -> None:
    assert len(serialize_stream(stream).decode().splitlines()) == len(stream)


def test_all_three_intent_kinds_are_present(stream) -> None:
    assert {i.kind for i in stream} == {KIND_LIMIT, KIND_MARKET, KIND_CANCEL}


def test_constant_size_cell_yields_unit_background_orders(cfg) -> None:
    unit = dataclasses.replace(cfg, size_distribution={"1": 1.0})
    later = [i for i in generate_stream(unit, SENTINEL[0], 3000)[10:] if i.kind == KIND_LIMIT]
    assert {i.size for i in later} == {1}
