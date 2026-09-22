"""Aggregation, paired bootstrap, and the decision rule.

The decision metric is Perold shortfall over the whole parent order, so it is
defined for every retained run including zero-fill. Every seed pair is therefore
complete by construction and there is nothing to exclude or impute; a missing
arm is a bug, not a data condition, and fails closed.

Inference is paired by seed on d_s = IS_PRO_RATA(s) - IS_FIFO(s). The arms are
never resampled independently.

The three non-NULL labels are numerical and are evaluated only when NULL does
not hold, which keeps a NULL result from also being a stop condition:

  UNSTABLE          exact two-sided binomial sign test on the signs of d_s
                    gives p > 0.05 (for 30 non-zero pairs, minority count >= 10)
  LATENCY_DRIVEN    CI at 0 ms contains zero AND |D0| <= 0.5 * |D5|
  ASSUMPTION_DRIVEN same, with the constant_order_size cell in place of 0 ms

Labels may overlap; all that hold are reported and the headline verdict is the
first in precedence order.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb, erf, sqrt

import numpy as np


NULL = "NULL"
UNSTABLE = "UNSTABLE"
LATENCY_DRIVEN = "LATENCY_DRIVEN"
ASSUMPTION_DRIVEN = "ASSUMPTION_DRIVEN"
DIFFERENCE = "DIFFERENCE_DETECTED"

PRECEDENCE = [NULL, UNSTABLE, LATENCY_DRIVEN, ASSUMPTION_DRIVEN, DIFFERENCE]


@dataclass
class Interval:
    point: float
    low: float
    high: float
    n: int
    contains_zero: bool


def distribution_summary(values: list[float | None]) -> dict:
    """Spread of the values, not just the mean."""
    clean = [v for v in values if v is not None]
    if not clean:
        return {"n": 0, "n_undefined": len(values), "mean": None, "median": None,
                "iqr": None, "p5": None, "p95": None}
    arr = np.asarray(clean, dtype=float)
    return {
        "n": int(arr.size),
        "n_undefined": len(values) - int(arr.size),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "iqr": float(np.percentile(arr, 75) - np.percentile(arr, 25)),
        "p5": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
    }


def sign_test_p(n_plus: int, n_minus: int) -> float:
    """Exact two-sided binomial sign test p-value."""
    n = n_plus + n_minus
    if n == 0:
        return 1.0
    k = min(n_plus, n_minus)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def bca_interval(diffs: np.ndarray, resamples: int, seed: int, alpha: float) -> Interval:
    """BCa bootstrap CI for the mean of the paired differences.

    alpha carries no default. The confidence level of the NULL rule is a frozen
    parameter and is read from the contract, not from a keyword here.
    """
    n = diffs.size
    if n < 3:
        raise ValueError(f"bootstrap needs at least 3 paired differences, got {n}")
    observed = float(diffs.mean())

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(resamples, n))
    boot = diffs[idx].mean(axis=1)

    prop = float((boot < observed).mean())
    prop = min(max(prop, 1.0 / resamples), 1.0 - 1.0 / resamples)
    z0 = _ppf(prop)

    jack = np.array([np.delete(diffs, i).mean() for i in range(n)])
    jack_mean = jack.mean()
    num = float(((jack_mean - jack) ** 3).sum())
    den = float(6.0 * (((jack_mean - jack) ** 2).sum() ** 1.5))
    acc = num / den if den != 0 else 0.0

    def endpoint(z_alpha: float) -> float:
        adj = z0 + (z0 + z_alpha) / (1 - acc * (z0 + z_alpha))
        return float(np.percentile(boot, min(max(100.0 * _cdf(adj), 0.0), 100.0)))

    low, high = endpoint(_ppf(alpha / 2)), endpoint(_ppf(1 - alpha / 2))
    if low > high:
        low, high = high, low
    return Interval(observed, low, high, n, low <= 0.0 <= high)


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _ppf(p: float) -> float:
    """Inverse normal CDF by bisection. Saves pulling in scipy."""
    lo, hi = -8.0, 8.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def paired_differences(
    records: list[dict], latency_ms: int, cell: str, metric: str,
    expected_seeds: tuple[int, ...] | None = None,
) -> np.ndarray:
    """PRO_RATA minus FIFO per seed. Fails closed on anything unexpected.

    Checks seed identity, not merely count. Thirty records carrying the wrong
    seed values used to satisfy the completeness gate and produce a clean
    verdict. Duplicate records for the same (seed, mechanism) used to overwrite
    silently, last write wins. Non-finite differences used to reach numpy and
    surface as an internal percentile error rather than a check of our own.
    """
    by_seed: dict[int, dict[str, float | None]] = {}
    for r in records:
        if r["latency_ms"] != latency_ms or r["cell"] != cell:
            continue
        arm = by_seed.setdefault(r["seed"], {})
        if r["mechanism"] in arm:
            raise ValueError(
                f"duplicate record for seed={r['seed']} mechanism={r['mechanism']} "
                f"latency={latency_ms} cell={cell}: a run set must not contain repeats"
            )
        arm[r["mechanism"]] = r[metric]

    if expected_seeds is not None and by_seed and set(by_seed) != set(expected_seeds):
        unexpected = sorted(set(by_seed) - set(expected_seeds))
        missing = sorted(set(expected_seeds) - set(by_seed))
        raise ValueError(
            f"seed set mismatch in cell (latency={latency_ms}, {cell}): "
            f"unexpected {unexpected[:5]}, missing {missing[:5]}"
        )

    diffs: list[float] = []
    for seed in sorted(by_seed):
        arm = by_seed[seed]
        a, b = arm.get("FIFO"), arm.get("PRO_RATA")
        if a is None or b is None:
            raise ValueError(
                f"incomplete seed pair at seed={seed} latency={latency_ms} cell={cell}: "
                f"the decision metric is defined for every retained run, so this is a bug"
            )
        diffs.append(float(b) - float(a))
    out = np.asarray(diffs, dtype=float)
    if out.size and not np.isfinite(out).all():
        raise ValueError(
            f"non-finite decision-metric difference in cell (latency={latency_ms}, {cell}): "
            "NaN or infinity must never reach the decision rule"
        )
    return out


def decide(records: list[dict], cfg) -> dict:
    """Apply the frozen negative-result criteria to a finished run set."""
    metric = cfg.decision_metric_id
    baseline = cfg.matched_baseline_ms
    ratio_max = cfg.attenuation_ratio_max

    expected = len(cfg.confirmation_seeds)
    diffs = paired_differences(records, baseline, "main", metric, cfg.confirmation_seeds)
    if diffs.size != expected:
        raise ValueError(
            f"decision cell has {diffs.size} paired differences, expected {expected}; "
            "the decision metric is defined for every retained run, so this is a bug"
        )
    interval = bca_interval(diffs, cfg.bootstrap_resamples, cfg.bootstrap_seed, cfg.interval_alpha)

    n_plus = int((diffs > 0).sum())
    n_minus = int((diffs < 0).sum())
    p_sign = sign_test_p(n_plus, n_minus)

    def cell_interval(latency: int, cell: str) -> Interval:
        """No try/except: a missing or short control cell is a bug, and
        swallowing it would silently drop a negative-result label and upgrade
        the verdict toward the positive headline."""
        d = paired_differences(records, latency, cell, metric, cfg.confirmation_seeds)
        if d.size != expected:
            raise ValueError(f"cell (latency={latency}, {cell}) has {d.size} pairs, expected {expected}")
        return bca_interval(d, cfg.bootstrap_resamples, cfg.bootstrap_seed, cfg.interval_alpha)

    zero_ci = cell_interval(0, "main")
    robust_ci = cell_interval(baseline, "robustness")

    def attenuated(ci: Interval) -> bool:
        if interval.point == 0.0:
            return False
        return ci.contains_zero and abs(ci.point) <= ratio_max * abs(interval.point)

    criteria: list[str] = []
    if interval.contains_zero:
        criteria.append(NULL)
    else:
        if p_sign > cfg.unstable_sign_test_alpha:
            criteria.append(UNSTABLE)
        if attenuated(zero_ci):
            criteria.append(LATENCY_DRIVEN)
        if attenuated(robust_ci):
            criteria.append(ASSUMPTION_DRIVEN)

    verdict = next((label for label in PRECEDENCE if label in criteria), DIFFERENCE)
    return {
        "verdict": verdict,
        "criteria_met": criteria,
        "metric": metric,
        "compared_at_latency_ms": baseline,
        "pairing": "paired_by_seed",
        "point_estimate": interval.point,
        "ci_low": interval.low,
        "ci_high": interval.high,
        "ci_contains_zero": interval.contains_zero,
        "n_pairs": interval.n,
        "sign_counts": {"positive": n_plus, "negative": n_minus, "zero": int((diffs == 0).sum())},
        "sign_test_p": p_sign,
        "attenuation_ratio_max": ratio_max,
        "zero_latency": {
            "point": zero_ci.point, "ci": [zero_ci.low, zero_ci.high],
            "ratio": abs(zero_ci.point) / abs(interval.point) if interval.point else None,
        },
        "robustness": {
            "point": robust_ci.point, "ci": [robust_ci.low, robust_ci.high],
            "ratio": abs(robust_ci.point) / abs(interval.point) if interval.point else None,
        },
    }
