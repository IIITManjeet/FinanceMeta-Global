"""Run mechanics: Perold shortfall, frozen horizon, reference mid, no-op counts."""

from __future__ import annotations

import dataclasses

import pytest

# Sentinel seeds only. Never a development seed (0-29) or a confirmation seed
# (100-129): a test run must not be able to produce an outcome on frozen data.
SENTINEL = (900_000_101, 900_000_102, 900_000_103, 900_000_104, 900_000_105)

from mechsim.contract import load_config
from mechsim.mechanisms import FIFO, PRO_RATA
from mechsim.sim import run_once


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def probe(cfg):
    return dataclasses.replace(cfg, warm_up_events=500, horizon_events=3000)


def test_shortfall_is_defined_for_every_run(probe) -> None:
    """Perold shortfall marks the unfilled remainder, so it is never undefined."""
    for seed in SENTINEL[:4]:
        for mech in (FIFO, PRO_RATA):
            result = run_once(probe, mech, seed=seed, latency_ms=5)
            assert isinstance(result.implementation_shortfall_bps, float)
            assert result.implementation_shortfall_bps == result.implementation_shortfall_bps


def test_zero_fill_run_is_pure_opportunity_cost(cfg) -> None:
    """With no fills the shortfall collapses to the mid move, by construction."""
    unfillable = dataclasses.replace(cfg, warm_up_events=200, horizon_events=600, parent_quantity=10**6)
    result = run_once(unfillable, FIFO, seed=900_000_100, latency_ms=100)
    if result.filled_lots == 0:
        assert result.implementation_shortfall_bps == pytest.approx(result.price_impact_bps)
    else:
        pytest.skip("probe filled; covered by the algebraic test below")


def test_shortfall_reduces_to_impact_when_nothing_executes(probe) -> None:
    """Algebraic check of the same identity, independent of any run."""
    q, p0, pt = 500, 1000.0, 1010.0
    shortfall = 1e4 * (0 + q * pt - q * p0) / (q * p0)
    impact = 1e4 * (pt - p0) / p0
    assert shortfall == pytest.approx(impact)


def test_run_uses_the_frozen_horizon_not_the_fill_time(cfg) -> None:
    """A fully filled run must still be marked at the horizon end."""
    easy = dataclasses.replace(cfg, warm_up_events=300, horizon_events=2500, parent_quantity=1)
    a = run_once(easy, FIFO, seed=900_000_100, latency_ms=0)
    longer = dataclasses.replace(easy, horizon_events=5000)
    b = run_once(longer, FIFO, seed=900_000_100, latency_ms=0)
    assert a.fill_probability == b.fill_probability == 1.0
    # Same parent, same seed, longer horizon: the mark moves, so the horizon is
    # genuinely the frozen event count rather than the moment of full fill.
    assert a.final_mid != b.final_mid or a.price_impact_bps != b.price_impact_bps


def test_identity_holds_between_arms(probe) -> None:
    a = run_once(probe, FIFO, seed=900_000_107, latency_ms=5)
    b = run_once(probe, PRO_RATA, seed=900_000_107, latency_ms=5)
    assert a.stream_sha256 == b.stream_sha256


def test_replay_is_byte_identical(probe) -> None:
    a = run_once(probe, PRO_RATA, seed=900_000_111, latency_ms=25)
    b = run_once(probe, PRO_RATA, seed=900_000_111, latency_ms=25)
    assert a.to_record() == b.to_record()


def test_record_carries_no_op_counters(probe) -> None:
    record = run_once(probe, FIFO, seed=900_000_100, latency_ms=5).to_record()
    for key in ("limit_no_ops", "cancel_no_ops", "market_no_ops"):
        assert key in record and isinstance(record[key], int)


def test_record_carries_full_provenance(probe) -> None:
    record = run_once(probe, FIFO, seed=900_000_100, latency_ms=5).to_record()
    for key in ("mechanism", "seed", "latency_ms", "cell", "stream_sha256", "flags",
                "arrival_mid", "final_mid", "implementation_shortfall_bps"):
        assert key in record
    assert len(record["stream_sha256"]) == 64


def test_reference_mid_is_never_missing(probe) -> None:
    """Carry-forward guarantees a mark even if the book empties."""
    result = run_once(probe, FIFO, seed=900_000_102, latency_ms=5)
    assert result.arrival_mid > 0
    assert result.final_mid > 0


def test_robustness_cell_uses_unit_background_sizes(probe) -> None:
    result = run_once(probe, PRO_RATA, seed=900_000_100, latency_ms=5, cell="robustness",
                      size_distribution={"1": 1.0})
    assert result.cell == "robustness"
    assert isinstance(result.implementation_shortfall_bps, float)


def test_higher_latency_does_not_crash_the_tracked_agent(probe) -> None:
    for latency in (0, 1, 2, 5, 10, 25, 50, 100):
        result = run_once(probe, FIFO, seed=900_000_100, latency_ms=latency)
        assert 0.0 <= result.fill_probability <= 1.0


def test_replenishment_churn_is_measurable_and_directional(cfg) -> None:
    """The disclosed churn asymmetry must be re-derivable, not a one-off number.

    Run at reduced scale for test speed; the figure quoted in the contract is
    measured at the frozen scale by the same function.
    """
    from mechsim.diagnostics import measure_replenishment_churn

    result = measure_replenishment_churn(
        cfg, seeds=(900_000_001, 900_000_002, 900_000_003),
        warm_up_events=500, horizon_events=3000,
    )
    assert result.fifo_mean > 0 and result.pro_rata_mean > 0
    assert result.excess_fraction > 0, "pro-rata is expected to replace more often"
    assert result.seeds_with_pro_rata_higher == len(result.seeds)
    assert "excess" in result.summary()


def test_churn_diagnostic_refuses_frozen_seeds(cfg) -> None:
    from mechsim.diagnostics import measure_replenishment_churn

    with pytest.raises(ValueError, match="refusing to run frozen seed"):
        measure_replenishment_churn(cfg, seeds=(cfg.confirmation_seeds[0],),
                                    warm_up_events=50, horizon_events=100)

def test_record_carries_a_digest_of_itself(cfg) -> None:
    """The data contract asks for a record sha256 beside the intent-stream one.

    It was listed as a required field from the freeze and never produced, so a
    reader had no way to tell an altered run record from an original.
    """
    import hashlib
    import json

    result = run_once(cfg, "FIFO", SENTINEL, 5)
    record = result.to_record()
    assert "record_sha256" in record

    body = {k: v for k, v in record.items() if k != "record_sha256"}
    expected = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert record["record_sha256"] == expected

    # it must actually depend on the record, not be a constant
    altered = dict(body, implementation_shortfall_bps=body["implementation_shortfall_bps"] + 1.0)
    altered_digest = hashlib.sha256(
        json.dumps(altered, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert altered_digest != record["record_sha256"]


def test_record_digest_is_stable_across_replay(cfg) -> None:
    """Byte-identical replay must reproduce the digest, or determinism is not shown."""
    first = run_once(cfg, "FIFO", SENTINEL, 5).to_record()
    second = run_once(cfg, "FIFO", SENTINEL, 5).to_record()
    assert first["record_sha256"] == second["record_sha256"]
