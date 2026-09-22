"""Decision-rule machinery: summaries, paired bootstrap, sign test, verdicts."""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import numpy as np
import pytest

from mechsim.analysis import (
    ASSUMPTION_DRIVEN,
    DIFFERENCE,
    LATENCY_DRIVEN,
    NULL,
    PRECEDENCE,
    UNSTABLE,
    bca_interval,
    decide,
    distribution_summary,
    paired_differences,
    sign_test_p,
)


# Seed labels only - nothing is executed here, but they stay out of frozen space.
SEEDS = tuple(900_000_300 + i for i in range(30))


def cfg(ratio_max: float = 0.5):
    return SimpleNamespace(
        matched_baseline_ms=5,
        bootstrap_resamples=600,
        bootstrap_seed=424242,
        attenuation_ratio_max=ratio_max,
        unstable_sign_test_alpha=0.05,
        interval_alpha=0.05,
        decision_metric_id="implementation_shortfall_bps",
        confirmation_seeds=SEEDS,
    )


def records(values: dict[tuple[int, str, str], list[float]]) -> list[dict]:
    """values[(latency, cell, mechanism)] -> per-seed decision-metric values.

    decide() now fails closed on a missing or short cell, so any cell not
    supplied is filled with a flat zero-difference series.
    """
    filled = dict(values)
    for latency, cell in ((5, "main"), (0, "main"), (5, "robustness")):
        for mech in ("FIFO", "PRO_RATA"):
            filled.setdefault((latency, cell, mech), [0.0] * len(SEEDS))
    out = []
    for (latency, cell, mech), series in filled.items():
        assert len(series) == len(SEEDS), "every cell must carry a full seed set"
        for seed, v in zip(SEEDS, series):
            out.append({
                "seed": seed, "latency_ms": latency, "cell": cell,
                "mechanism": mech, "implementation_shortfall_bps": v,
            })
    return out


# ---------------------------------------------------------------- summaries

def test_distribution_summary_reports_more_than_the_mean() -> None:
    summary = distribution_summary([1.0, 2.0, 3.0, 4.0])
    for key in ("median", "iqr", "p5", "p95"):
        assert summary[key] is not None


def test_distribution_summary_counts_undefined_values() -> None:
    summary = distribution_summary([1.0, None, 3.0, None])
    assert (summary["n"], summary["n_undefined"]) == (2, 2)


def test_distribution_summary_of_all_undefined_is_not_an_error() -> None:
    assert distribution_summary([None, None])["mean"] is None


# ------------------------------------------------------------------- pairing

def test_paired_differences_pairs_by_seed() -> None:
    r = [
        {"seed": SEEDS[0], "latency_ms": 5, "cell": "main", "mechanism": "FIFO", "implementation_shortfall_bps": 1.0},
        {"seed": SEEDS[0], "latency_ms": 5, "cell": "main", "mechanism": "PRO_RATA", "implementation_shortfall_bps": 4.0},
        {"seed": SEEDS[1], "latency_ms": 5, "cell": "main", "mechanism": "FIFO", "implementation_shortfall_bps": 2.0},
        {"seed": SEEDS[1], "latency_ms": 5, "cell": "main", "mechanism": "PRO_RATA", "implementation_shortfall_bps": 3.0},
    ]
    assert list(paired_differences(r, 5, "main", "implementation_shortfall_bps")) == [3.0, 1.0]


def test_incomplete_pair_fails_closed() -> None:
    """The metric is defined for every retained run, so a gap is a bug."""
    r = [
        {"seed": SEEDS[0], "latency_ms": 5, "cell": "main", "mechanism": "FIFO", "implementation_shortfall_bps": 1.0},
        {"seed": SEEDS[1], "latency_ms": 5, "cell": "main", "mechanism": "FIFO", "implementation_shortfall_bps": 2.0},
        {"seed": SEEDS[0], "latency_ms": 5, "cell": "main", "mechanism": "PRO_RATA", "implementation_shortfall_bps": 4.0},
    ]
    with pytest.raises(ValueError, match="incomplete seed pair"):
        paired_differences(r, 5, "main", "implementation_shortfall_bps")


def test_undefined_decision_metric_fails_closed() -> None:
    r = [
        {"seed": SEEDS[0], "latency_ms": 5, "cell": "main", "mechanism": "FIFO", "implementation_shortfall_bps": 1.0},
        {"seed": SEEDS[0], "latency_ms": 5, "cell": "main", "mechanism": "PRO_RATA", "implementation_shortfall_bps": None},
    ]
    with pytest.raises(ValueError):
        paired_differences(r, 5, "main", "implementation_shortfall_bps")


def test_paired_differences_ignores_other_cells_and_latencies() -> None:
    r = [
        {"seed": SEEDS[0], "latency_ms": 0, "cell": "main", "mechanism": "FIFO", "implementation_shortfall_bps": 1.0},
        {"seed": SEEDS[0], "latency_ms": 0, "cell": "main", "mechanism": "PRO_RATA", "implementation_shortfall_bps": 9.0},
    ]
    assert paired_differences(r, 5, "main", "implementation_shortfall_bps").size == 0


# ----------------------------------------------------------------- sign test

def test_single_opposite_seed_does_not_look_unstable() -> None:
    """The reviewer's objection: one noisy seed must not trigger UNSTABLE."""
    assert sign_test_p(29, 1) < 0.05


def test_nine_of_thirty_is_still_consistent() -> None:
    assert sign_test_p(21, 9) < 0.05


def test_ten_of_thirty_is_unstable() -> None:
    assert sign_test_p(20, 10) > 0.05


def test_even_split_is_maximally_unstable() -> None:
    assert sign_test_p(15, 15) == pytest.approx(1.0)


def test_sign_test_is_symmetric_and_handles_empty() -> None:
    assert sign_test_p(20, 10) == sign_test_p(10, 20)
    assert sign_test_p(0, 0) == 1.0


# ----------------------------------------------------------------- bootstrap

def test_bca_interval_on_zero_centred_noise_contains_zero() -> None:
    diffs = np.random.default_rng(0).normal(0.0, 1.0, size=40)
    assert bca_interval(diffs, resamples=800, seed=424242, alpha=0.05).contains_zero


def test_bca_interval_on_a_large_shift_excludes_zero() -> None:
    diffs = np.random.default_rng(1).normal(25.0, 1.0, size=40)
    assert not bca_interval(diffs, resamples=800, seed=424242, alpha=0.05).contains_zero


def test_bca_interval_is_deterministic_for_a_fixed_seed() -> None:
    diffs = np.linspace(-1.0, 3.0, 30)
    a = bca_interval(diffs, resamples=500, seed=424242, alpha=0.05)
    b = bca_interval(diffs, resamples=500, seed=424242, alpha=0.05)
    assert (a.low, a.high, a.point) == (b.low, b.high, b.point)


def test_interval_alpha_has_no_default_and_comes_from_the_contract() -> None:
    """The confidence level of the NULL rule was a keyword default in source; the
    contract carried it only as prose. It is a field now, loaded with no default."""
    from mechsim.contract import DEFAULT_CONTRACT, load_config
    assert inspect.signature(bca_interval).parameters["alpha"].default is inspect.Parameter.empty
    contract = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
    assert load_config().interval_alpha == contract["metrics"]["decision_metric"]["interval_alpha"] == 0.05


def test_decide_passes_the_contract_alpha_to_the_bootstrap() -> None:
    """A wider alpha must visibly narrow the reported interval, or decide() is not using it."""
    noise = list(np.random.default_rng(15).normal(0.0, 1.0, size=30))
    r = records({(5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): noise})
    narrow, wide = cfg(), cfg()
    narrow.interval_alpha, wide.interval_alpha = 0.5, 0.05
    a, b = decide(r, narrow), decide(r, wide)
    assert (a["ci_high"] - a["ci_low"]) < (b["ci_high"] - b["ci_low"])


def test_decide_uses_the_contract_attenuation_ratio() -> None:
    """Config carried the ratio, but nothing showed decide() read it: a literal
    0.5 in place of cfg.attenuation_ratio_max passed every test. The zero-latency
    cell here sits at a tenth of the baseline effect with an interval through
    zero, so LATENCY_DRIVEN must appear at 0.5 and vanish at 0.02."""
    big = list(np.random.default_rng(16).normal(50.0, 1.0, size=30))
    tenth = [25.0] * 15 + [-15.0] * 15
    r = records({
        (5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): big,
        (0, "main", "FIFO"): [0.0] * 30, (0, "main", "PRO_RATA"): tenth,
    })
    loose, tight = decide(r, cfg(ratio_max=0.5)), decide(r, cfg(ratio_max=0.02))
    assert loose["zero_latency"]["ratio"] == pytest.approx(0.1, abs=0.02)
    assert LATENCY_DRIVEN in loose["criteria_met"]
    assert LATENCY_DRIVEN not in tight["criteria_met"]
    assert (loose["attenuation_ratio_max"], tight["attenuation_ratio_max"]) == (0.5, 0.02)


def test_decide_uses_the_contract_sign_test_alpha() -> None:
    """Same class as the ratio: a literal 0.05 in place of
    cfg.unstable_sign_test_alpha passed every test. Twenty positive and ten
    negative pairs give p of about 0.099, so UNSTABLE must appear at 0.05 and
    not at 0.2, with the interval clear of zero either way."""
    split = [10.0] * 20 + [-1.0] * 10
    r = records({(5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): split})
    strict, lax = cfg(), cfg()
    strict.unstable_sign_test_alpha, lax.unstable_sign_test_alpha = 0.05, 0.2
    a, b = decide(r, strict), decide(r, lax)
    assert not a["ci_contains_zero"] and 0.05 < a["sign_test_p"] < 0.2
    assert a["verdict"] == UNSTABLE
    assert UNSTABLE not in b["criteria_met"]


# ------------------------------------------------------------------ verdicts

def test_null_when_the_interval_straddles_zero() -> None:
    noise = list(np.random.default_rng(3).normal(0.0, 1.0, size=30))
    r = records({(5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): noise})
    assert decide(r, cfg())["verdict"] == NULL


def test_null_suppresses_the_other_labels() -> None:
    """A NULL result must never also be a stop condition."""
    alternating = [1.0 if i % 2 else -1.0 for i in range(30)]
    r = records({(5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): alternating})
    out = decide(r, cfg())
    assert out["verdict"] == NULL
    assert UNSTABLE not in out["criteria_met"]


def test_difference_detected_when_effect_is_large_and_consistent() -> None:
    """Effect persists at 0 ms and in the robustness cell, so nothing attenuates it."""
    rng = np.random.default_rng(4)
    r = records({
        (5, "main", "PRO_RATA"): list(rng.normal(50.0, 1.0, size=30)),
        (0, "main", "PRO_RATA"): list(rng.normal(48.0, 1.0, size=30)),
        (5, "robustness", "PRO_RATA"): list(rng.normal(49.0, 1.0, size=30)),
    })
    out = decide(r, cfg())
    assert out["verdict"] == DIFFERENCE, out["criteria_met"]


def test_latency_driven_requires_both_clauses() -> None:
    big = list(np.random.default_rng(5).normal(50.0, 1.0, size=30))
    tiny = list(np.random.default_rng(6).normal(0.0, 1.0, size=30))
    r = records({
        (5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): big,
        (0, "main", "FIFO"): [0.0] * 30, (0, "main", "PRO_RATA"): tiny,
    })
    assert LATENCY_DRIVEN in decide(r, cfg())["criteria_met"]


def test_latency_driven_does_not_fire_when_the_effect_persists() -> None:
    big = list(np.random.default_rng(7).normal(50.0, 1.0, size=30))
    still_big = list(np.random.default_rng(8).normal(48.0, 1.0, size=30))
    r = records({
        (5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): big,
        (0, "main", "FIFO"): [0.0] * 30, (0, "main", "PRO_RATA"): still_big,
    })
    assert LATENCY_DRIVEN not in decide(r, cfg())["criteria_met"]


def test_assumption_driven_uses_the_robustness_cell() -> None:
    big = list(np.random.default_rng(9).normal(50.0, 1.0, size=30))
    tiny = list(np.random.default_rng(10).normal(0.0, 1.0, size=30))
    r = records({
        (5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): big,
        (5, "robustness", "FIFO"): [0.0] * 30, (5, "robustness", "PRO_RATA"): tiny,
    })
    assert ASSUMPTION_DRIVEN in decide(r, cfg())["criteria_met"]


def test_overlapping_labels_are_all_reported_and_precedence_decides() -> None:
    big = list(np.random.default_rng(11).normal(50.0, 1.0, size=30))
    tiny_a = list(np.random.default_rng(12).normal(0.0, 1.0, size=30))
    tiny_b = list(np.random.default_rng(13).normal(0.0, 1.0, size=30))
    r = records({
        (5, "main", "FIFO"): [0.0] * 30, (5, "main", "PRO_RATA"): big,
        (0, "main", "FIFO"): [0.0] * 30, (0, "main", "PRO_RATA"): tiny_a,
        (5, "robustness", "FIFO"): [0.0] * 30, (5, "robustness", "PRO_RATA"): tiny_b,
    })
    out = decide(r, cfg())
    assert {LATENCY_DRIVEN, ASSUMPTION_DRIVEN}.issubset(set(out["criteria_met"]))
    assert out["verdict"] == LATENCY_DRIVEN


def test_precedence_order_is_the_frozen_one() -> None:
    assert PRECEDENCE == [NULL, UNSTABLE, LATENCY_DRIVEN, ASSUMPTION_DRIVEN, DIFFERENCE]


def test_decision_reports_pairing_and_sign_counts() -> None:
    rng = np.random.default_rng(14)
    out = decide(records({
        (5, "main", "PRO_RATA"): list(rng.normal(50.0, 1.0, size=30)),
        (0, "main", "PRO_RATA"): list(rng.normal(48.0, 1.0, size=30)),
        (5, "robustness", "PRO_RATA"): list(rng.normal(49.0, 1.0, size=30)),
    }), cfg())
    assert out["pairing"] == "paired_by_seed"
    assert out["sign_counts"]["positive"] + out["sign_counts"]["negative"] == 30


# --- fail-closed guards added after the second adversarial audit -------------

def test_seed_identity_is_checked_not_just_count() -> None:
    """Thirty records on the wrong seeds used to produce a clean verdict."""
    wrong = tuple(900_000_500 + i for i in range(30))
    r = [
        {"seed": s, "latency_ms": lat, "cell": cell, "mechanism": m,
         "implementation_shortfall_bps": 5.0 if m == "PRO_RATA" else 1.0}
        for lat, cell in ((5, "main"), (0, "main"), (5, "robustness"))
        for s in wrong for m in ("FIFO", "PRO_RATA")
    ]
    with pytest.raises(ValueError, match="seed set mismatch"):
        decide(r, cfg())


def test_duplicate_records_are_rejected() -> None:
    """Last-write-wins silently corrupted the statistic."""
    r = [
        {"seed": SEEDS[0], "latency_ms": 5, "cell": "main", "mechanism": "FIFO",
         "implementation_shortfall_bps": v}
        for v in (1.0, 999.0)
    ]
    with pytest.raises(ValueError, match="must not contain repeats"):
        paired_differences(r, 5, "main", "implementation_shortfall_bps")


def test_non_finite_differences_are_rejected() -> None:
    """Protection used to be an accident of numpy's percentile bounds check."""
    r = []
    for s in SEEDS:
        for m in ("FIFO", "PRO_RATA"):
            bad = float("nan") if (s == SEEDS[0] and m == "FIFO") else 1.0
            r.append({"seed": s, "latency_ms": 5, "cell": "main", "mechanism": m,
                      "implementation_shortfall_bps": bad})
    with pytest.raises(ValueError, match="non-finite"):
        paired_differences(r, 5, "main", "implementation_shortfall_bps", SEEDS)


def test_infinite_differences_are_rejected() -> None:
    r = []
    for s in SEEDS:
        for m in ("FIFO", "PRO_RATA"):
            bad = float("inf") if m == "PRO_RATA" else 1.0
            r.append({"seed": s, "latency_ms": 5, "cell": "main", "mechanism": m,
                      "implementation_shortfall_bps": bad})
    with pytest.raises(ValueError, match="non-finite"):
        paired_differences(r, 5, "main", "implementation_shortfall_bps", SEEDS)
