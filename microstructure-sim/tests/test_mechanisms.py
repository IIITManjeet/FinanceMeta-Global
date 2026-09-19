"""Allocation mechanism tests, including the frozen analytic sanity case."""

from __future__ import annotations

import pytest

from mechsim.mechanisms import FIFO, PRO_RATA, Resting, allocate


def test_frozen_analytic_sanity_case_fifo() -> None:
    """Contract control 3: 6-lot aggressor vs X=2 (seq 1), Y=10 (seq 2)."""
    resting = [Resting(1, 2, 1), Resting(2, 10, 2)]
    assert allocate(FIFO, resting, 6) == {1: 2, 2: 4}


def test_frozen_analytic_sanity_case_pro_rata() -> None:
    resting = [Resting(1, 2, 1), Resting(2, 10, 2)]
    assert allocate(PRO_RATA, resting, 6) == {1: 1, 2: 5}


@pytest.mark.parametrize("mechanism", [FIFO, PRO_RATA])
def test_allocation_never_exceeds_demand(mechanism: str) -> None:
    resting = [Resting(1, 5, 1), Resting(2, 7, 2), Resting(3, 3, 3)]
    for demand in range(0, 20):
        allocation = allocate(mechanism, resting, demand)
        assert sum(allocation.values()) <= demand


@pytest.mark.parametrize("mechanism", [FIFO, PRO_RATA])
def test_allocation_never_exceeds_resting_size(mechanism: str) -> None:
    resting = [Resting(1, 5, 1), Resting(2, 7, 2), Resting(3, 3, 3)]
    caps = {o.order_id: o.size for o in resting}
    for demand in range(0, 20):
        for order_id, lots in allocate(mechanism, resting, demand).items():
            assert lots <= caps[order_id]


@pytest.mark.parametrize("mechanism", [FIFO, PRO_RATA])
def test_demand_at_or_above_total_fills_everyone(mechanism: str) -> None:
    resting = [Resting(1, 5, 1), Resting(2, 7, 2)]
    assert allocate(mechanism, resting, 12) == {1: 5, 2: 7}
    assert allocate(mechanism, resting, 99) == {1: 5, 2: 7}


@pytest.mark.parametrize("mechanism", [FIFO, PRO_RATA])
def test_empty_inputs_allocate_nothing(mechanism: str) -> None:
    assert allocate(mechanism, [], 10) == {}
    assert allocate(mechanism, [Resting(1, 5, 1)], 0) == {}


def test_fifo_respects_strict_arrival_order() -> None:
    resting = [Resting(9, 4, 3), Resting(7, 4, 1), Resting(8, 4, 2)]
    # Demand of 6 must exhaust seq 1 then partially fill seq 2, ignoring size.
    assert allocate(FIFO, resting, 6) == {7: 4, 8: 2}


def test_fifo_is_insensitive_to_size_ordering() -> None:
    small_first = [Resting(1, 1, 1), Resting(2, 100, 2)]
    assert allocate(FIFO, small_first, 1) == {1: 1}


def test_pro_rata_is_sensitive_to_size() -> None:
    """The defining difference: a larger resting order gets a larger share."""
    resting = [Resting(1, 1, 1), Resting(2, 9, 2)]
    allocation = allocate(PRO_RATA, resting, 10)
    assert allocation[2] > allocation[1]


def test_pro_rata_conserves_supply_exactly_when_capacity_allows() -> None:
    resting = [Resting(1, 10, 1), Resting(2, 10, 2), Resting(3, 10, 3)]
    for demand in range(1, 30):
        assert sum(allocate(PRO_RATA, resting, demand).values()) == demand


def test_pro_rata_largest_remainder_breaks_ties_by_arrival_seq() -> None:
    """Equal sizes, odd demand: the earlier arrival takes the extra lot."""
    resting = [Resting(1, 5, 1), Resting(2, 5, 2)]
    allocation = allocate(PRO_RATA, resting, 5)
    assert allocation[1] == 3
    assert allocation[2] == 2


def test_pro_rata_starves_an_order_below_the_minimum_allocation() -> None:
    """A share below one whole lot receives nothing - a participation floor,
    not a guaranteed allocation."""
    resting = [Resting(1, 1, 1), Resting(2, 1000, 2)]
    allocation = allocate(PRO_RATA, resting, 500)
    assert allocation.get(1, 0) == 0
    assert allocation[2] == 500


def test_pro_rata_awards_whole_lots_by_remainder_when_shares_are_fractional() -> None:
    """Three equal orders splitting two lots: the two earliest take them."""
    resting = [Resting(1, 1, 1), Resting(2, 1, 2), Resting(3, 1, 3)]
    allocation = allocate(PRO_RATA, resting, 2)
    assert allocation == {1: 1, 2: 1}


def test_mechanisms_disagree_on_a_size_heterogeneous_book() -> None:
    """Sanity: the two rules are genuinely different functions."""
    resting = [Resting(1, 1, 1), Resting(2, 50, 2)]
    assert allocate(FIFO, resting, 10) != allocate(PRO_RATA, resting, 10)


def test_unknown_mechanism_is_rejected() -> None:
    with pytest.raises(ValueError):
        allocate("FREQUENT_BATCH_AUCTION", [Resting(1, 1, 1)], 1)
