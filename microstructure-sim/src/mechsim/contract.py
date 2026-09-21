"""Load the contract JSON into a Config.

The contract is the only source for frozen parameters. Nothing here carries a
default, so a missing field raises instead of quietly substituting something.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "evaluation/microstructure-mechanism-2026-09/experiment_contract.json"
)


@dataclass(frozen=True)
class Config:
    contract_id: str
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
    # seeds
    seeds: tuple[int, ...]
    confirmation_seeds: tuple[int, ...]
    bootstrap_seed: int
    bootstrap_resamples: int
    # fees
    maker_bps: float
    taker_bps: float
    # decision rule
    attenuation_ratio_max: float
    unstable_sign_test_alpha: float

    @property
    def total_events(self) -> int:
        return self.warm_up_events + self.horizon_events


def load_config(contract_path: Path | str | None = None) -> Config:
    path = Path(contract_path) if contract_path else DEFAULT_CONTRACT
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    flow = data["order_flow"]
    book = data["initial_book_state"]
    tracked = data["participants"]["tracked_agent"]
    latency = data["latency"]
    seeds = data["seed_policy"]
    fees = data["fees"]
    decision = data["metrics"]["decision_metric"]
    negative = data["negative_result_criteria"]

    return Config(
        contract_id=data["contract_id"],
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
        robustness_latency_ms=int(data["robustness_cell"]["applies_at_latency_ms"]),
        seeds=tuple(int(s) for s in seeds["seeds"]),
        confirmation_seeds=tuple(int(s) for s in seeds["confirmation_seeds"]),
        bootstrap_seed=int(seeds["bootstrap_seed"]),
        bootstrap_resamples=int(decision["bootstrap_resamples"]),
        maker_bps=float(fees["maker_bps"]),
        taker_bps=float(fees["taker_bps"]),
        attenuation_ratio_max=float(negative["LATENCY_DRIVEN"]["attenuation_ratio_max"]),
        unstable_sign_test_alpha=float(negative["UNSTABLE"]["alpha"]),
    )
