"""Load the contract JSON into a Config.

The contract is the only source for frozen parameters. Nothing here carries a
default, so a missing field raises instead of quietly substituting something.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


CONTRACT_PATH_IN_REPO = "evaluation/microstructure-mechanism-2026-09/experiment_contract.json"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTRACT = REPO_ROOT / CONTRACT_PATH_IN_REPO


@dataclass(frozen=True)
class Config:
    contract_id: str
    # sha256 of the bytes this configuration was loaded from. The frozen-seed
    # grant is keyed on it, so a contract that merely shares an id is not
    # covered by a receipt validated for another set of bytes.
    contract_sha256: str
    decision_metric_id: str
    not_differenced: frozenset[str]
    # mechanisms
    min_allocation_lots: int
    # order flow
    limit_rate_per_level: float
    levels: int
    market_rate_per_side: float
    cancel_rate_per_lot: float
    size_distribution: dict[str, float]
    tick: int
    initial_mid: int
    # initial book
    levels_per_side: int
    lots_per_level: int
    ladder_bid_prices: tuple[int, ...]
    ladder_ask_prices: tuple[int, ...]
    warm_up_events: int
    horizon_events: int
    # participants
    parent_quantity: int
    display_lots: int
    # latency
    latency_grid: tuple[int, ...]
    background_latency_ms: int
    matched_baseline_ms: int
    robustness_latency_ms: int
    robustness_size_distribution: dict[str, float]
    # seeds
    seeds: tuple[int, ...]
    confirmation_seeds: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_resamples: int
    interval_alpha: float
    # fees
    maker_bps: float
    taker_bps: float
    # decision rule
    attenuation_ratio_max: float
    unstable_sign_test_alpha: float

    @property
    def total_events(self) -> int:
        return self.warm_up_events + self.horizon_events

    def identity(self) -> str:
        """Digest of every frozen field, so a derived configuration is not this one.

        The grant used to key on the contract id and the file digest alone,
        both of which dataclasses.replace copies unchanged while altering the
        scale, the seeds or the horizon. Hashing the fields means a derived
        configuration does not inherit the authorisation.
        """
        # the dataclass repr names every field and its value, and needs neither
        # __dict__ nor a computed getattr, which the package forbids itself
        return hashlib.sha256(repr(self).encode("utf-8")).hexdigest()


def committed_canonical_seeds(root: Path = REPO_ROOT) -> frozenset[int]:
    """Frozen seeds listed by the canonical contract as committed at HEAD.

    Read from git rather than from disk, so an in-place edit of the working
    file cannot shrink the set. This is a contribution to a union, never a
    gate of its own: without git, outside a checkout, or with nothing
    committed at the path it returns nothing and the on-disk copies still
    apply. A committed copy that does not parse contributes nothing too.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "show", f"HEAD:{CONTRACT_PATH_IN_REPO}"], capture_output=True, check=False
        )
    except OSError:
        return frozenset()
    if done.returncode != 0:
        return frozenset()
    try:
        policy = json.loads(done.stdout.decode("utf-8"))["seed_policy"]
        return frozenset(int(s) for s in (*policy["seeds"], *policy["confirmation_seeds"]))
    except (ValueError, KeyError, TypeError):
        return frozenset()


def frozen_seeds(cfg: Config) -> frozenset[int]:
    """Seeds that only the authorised confirmatory run may execute.

    The union of three sets: the loaded contract's, the canonical in-repo
    contract's as it is on disk, and the canonical contract's as committed at
    HEAD. Reading the sets from whatever contract the caller passed let a copy
    with empty seed lists execute development seed 0 through the CLI; reading
    them from the canonical file alone left that file itself as an unverified
    anchor, since nothing outside the receipt gate checks it against git and
    an in-place edit emptied the set. A union degrades safely: with no git the
    first two still hold, and with a doctored working file the committed copy
    still lists every frozen seed. If the canonical file on disk cannot be
    read this raises, refusing everything rather than protecting less.
    """
    canonical = load_config(DEFAULT_CONTRACT)
    return frozenset(
        (*cfg.seeds, *cfg.confirmation_seeds, *canonical.seeds, *canonical.confirmation_seeds)
    ) | committed_canonical_seeds()


def load_config(contract_path: Path | str | None = None) -> Config:
    path = Path(contract_path) if contract_path else DEFAULT_CONTRACT
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))

    flow = data["order_flow"]
    book = data["initial_book_state"]
    tracked = data["participants"]["tracked_agent"]
    latency = data["latency"]
    robustness = data["robustness_cell"]
    seeds = data["seed_policy"]
    fees = data["fees"]
    decision = data["metrics"]["decision_metric"]
    negative = data["negative_result_criteria"]

    known = {str(m["id"]) for m in data["metrics"]["primary"]}
    if str(decision["id"]) not in known and str(decision["id"]) != "implementation_shortfall_bps":
        raise ValueError(
            f"decision metric {decision['id']!r} is not one of the primary metrics {sorted(known)}"
        )
    return Config(
        contract_id=data["contract_id"],
        contract_sha256=hashlib.sha256(raw).hexdigest(),
        decision_metric_id=str(decision["id"]),
        not_differenced=frozenset(data["metrics"]["not_differenced_across_mechanisms"]),
        min_allocation_lots=int(data["mechanisms"]["B"]["min_allocation_lots"]),
        limit_rate_per_level=float(flow["limit_order_rate_per_level_per_sec"]),
        levels=int(flow["levels_from_opposite_best"]),
        market_rate_per_side=float(flow["market_order_rate_per_side_per_sec"]),
        cancel_rate_per_lot=float(flow["cancel_rate_per_resting_lot_per_sec"]),
        size_distribution=dict(flow["order_size_distribution_lots"]),
        tick=int(flow["tick_size"]),
        initial_mid=int(flow["initial_mid_price"]),
        levels_per_side=int(book["levels_per_side"]),
        lots_per_level=int(book["lots_per_level"]),
        ladder_bid_prices=tuple(int(x) for x in book["ladder"]["bid_prices"]),
        ladder_ask_prices=tuple(int(x) for x in book["ladder"]["ask_prices"]),
        warm_up_events=int(book["warm_up_events_discarded"]),
        horizon_events=int(data["horizon"]["events_per_run_after_warm_up"]),
        parent_quantity=int(tracked["parent_quantity_lots"]),
        display_lots=int(tracked["display_lots"]),
        latency_grid=tuple(int(x) for x in latency["tracked_agent_one_way_ms"]),
        background_latency_ms=int(latency["background_one_way_ms"]),
        matched_baseline_ms=int(latency["matched_baseline_ms"]),
        robustness_latency_ms=int(robustness["applies_at_latency_ms"]),
        robustness_size_distribution=dict(robustness["order_size_distribution_lots"]),
        seeds=tuple(int(s) for s in seeds["seeds"]),
        confirmation_seeds=tuple(int(s) for s in seeds["confirmation_seeds"]),
        bootstrap_seed=int(seeds["bootstrap_seed"]),
        bootstrap_resamples=int(decision["bootstrap_resamples"]),
        interval_alpha=float(decision["interval_alpha"]),
        maker_bps=float(fees["maker_bps"]),
        taker_bps=float(fees["taker_bps"]),
        attenuation_ratio_max=float(negative["LATENCY_DRIVEN"]["attenuation_ratio_max"]),
        unstable_sign_test_alpha=float(negative["UNSTABLE"]["alpha"]),
    )
