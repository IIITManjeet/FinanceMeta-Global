#!/usr/bin/env python3
"""Fail-closed validator for the FinanceMeta market-microstructure mechanism contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "evaluation/microstructure-mechanism-2026-09/experiment_contract.json"
PROTOCOL_DOC = ROOT / "evaluation/microstructure-mechanism-2026-09/PROTOCOL.md"

CONTRACT_ID = "FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v1"
FROZEN_DATE = "2026-09-19"

EXPECTED_MECHANISM_IDS = {"FIFO", "PRO_RATA"}
EXPECTED_SEEDS = list(range(30))
EXPECTED_LATENCY_GRID = [0, 1, 2, 5, 10, 25, 50, 100]
MATCHED_BASELINE_MS = 5

EXPECTED_PRIMARY_METRICS = {
    "fill_probability",
    "implementation_shortfall_bps",
    "spread_at_execution_ticks",
    "queue_and_wait",
    "price_impact_bps",
}

REQUIRED_CONTROLS = {
    "identity_run",
    "zero_latency_control",
    "analytic_sanity_case",
    "deterministic_replay",
}

REQUIRED_NEGATIVE_CRITERIA = {
    "NULL",
    "UNSTABLE",
    "LATENCY_DRIVEN",
    "ASSUMPTION_DRIVEN",
}

REQUIRED_PROHIBITED_CLAIMS = {
    "real-market alpha",
    "live execution performance",
    "universal market-quality superiority",
    "investor benefit",
    "exchange deployability from simulation alone",
    "any claim that either mechanism is a superior market design",
    "cross-reference to unrelated prior auction or mechanism-design work by the builder",
}

PROTOCOL_SAFEGUARDS = (
    "synthetic simulation only",
    "negative result is a valid completion",
    "no third mechanism is added after a null result",
    "strategic size inflation",
    "state-independent",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate(data: dict[str, object], doc_path: Path = PROTOCOL_DOC) -> None:
    require(data.get("contract_id") == CONTRACT_ID, "contract ID drift")
    require(data.get("status") == "FROZEN_PRE_RESULT", "contract must remain frozen pre-result")
    require(data.get("frozen_date") == FROZEN_DATE, "freeze date drift")

    authority = data["authority"]
    require(authority["builder"] == "Manjeet Pathak", "builder attribution removed or altered")
    sha = authority["freeze_commit_sha"]
    require(sha is None or (len(str(sha)) == 40 and str(sha).isalnum()), "freeze SHA must be full 40-character or null")

    freeze = data["freeze"]
    require(freeze["results_inspected"] is False, "results cannot be inspected before the main run")
    require(freeze["simulator_implemented_at_freeze"] is False, "simulator must not exist at brief freeze")
    require(freeze["parameters_may_change_after_results"] is False, "post-result parameter change cannot be permitted")
    require(
        freeze["third_mechanism_may_be_added_after_results"] is False,
        "a third mechanism cannot be admitted after results",
    )
    require(isinstance(freeze["amendments"], list), "amendment log must be a list")

    mechanisms = data["mechanisms"]
    require(mechanisms["count"] == 2, "exactly two mechanisms are permitted in the first pass")
    require(
        {mechanisms["A"]["id"], mechanisms["B"]["id"]} == EXPECTED_MECHANISM_IDS,
        "mechanism pair drift",
    )
    require(mechanisms["B"]["min_allocation_lots"] == 1, "pro-rata minimum allocation drift")
    require(mechanisms["B"]["rounding"] == "largest_remainder", "pro-rata rounding rule drift")

    flow = data["order_flow"]
    require(flow["state_independent"] is True, "order flow must remain state-independent for a provable identity run")
    require(flow["generator"] == "zero_intelligence_poisson", "order-flow generator drift")

    seeds = data["seed_policy"]
    require(seeds["seeds"] == EXPECTED_SEEDS, "seed policy drift")
    require(seeds["seed_count"] == len(EXPECTED_SEEDS), "seed count inconsistent with seed list")
    require(seeds["failed_seeds_may_be_discarded"] is False, "failed seeds cannot be discarded")

    latency = data["latency"]
    require(latency["tracked_agent_one_way_ms"] == EXPECTED_LATENCY_GRID, "latency sweep drift")
    require(latency["matched_baseline_ms"] == MATCHED_BASELINE_MS, "matched-latency baseline drift")
    require(MATCHED_BASELINE_MS in EXPECTED_LATENCY_GRID, "matched baseline must lie on the swept grid")

    fees = data["fees"]
    require(fees["maker_bps"] == 0.0 and fees["taker_bps"] == 0.0, "fee schedule drift")

    metrics = data["metrics"]
    primary_ids = {entry["id"] for entry in metrics["primary"]}
    require(primary_ids == EXPECTED_PRIMARY_METRICS, "primary metric set drift")
    require(len(metrics["primary"]) == 5, "all five primary metrics must be retained")
    require(metrics["all_primary_reported_every_run"] is True, "all primary metrics must be reported every run")
    require(metrics["means_only_reporting_permitted"] is False, "means-only reporting cannot be permitted")
    require(
        set(metrics["distributional_summaries_required"]) == {"median", "iqr", "p5", "p95"},
        "distributional summary requirement drift",
    )

    decision = metrics["decision_metric"]
    require(decision["id"] == "implementation_shortfall_bps", "decision metric drift")
    require(decision["direction"] == "lower_is_better", "decision metric direction drift")
    require(decision["compared_at_latency_ms"] == MATCHED_BASELINE_MS, "decision metric comparison point drift")
    require(decision["bootstrap_resamples"] == 10000, "bootstrap resample count drift")

    controls = data["controls"]
    require(set(controls) == REQUIRED_CONTROLS, "required control set drift")
    sanity = controls["analytic_sanity_case"]
    require(
        sanity["expected_fifo_allocation_lots"] == {"X": 2, "Y": 4},
        "analytic FIFO allocation drift",
    )
    require(
        sanity["expected_pro_rata_allocation_lots"] == {"X": 1, "Y": 5},
        "analytic pro-rata allocation drift",
    )

    robustness = data["robustness_cell"]
    require(robustness["count"] == 1, "exactly one prespecified robustness cell is permitted")
    require(robustness["id"] == "constant_order_size", "robustness cell drift")

    matrix = data["run_matrix"]
    main = matrix["main"]
    expected_main = main["mechanisms"] * main["latency_points"] * main["seeds"]
    require(main["runs"] == expected_main, "main run count inconsistent with its own grid")
    robust = matrix["robustness"]
    expected_robust = robust["mechanisms"] * robust["latency_points"] * robust["seeds"]
    require(robust["runs"] == expected_robust, "robustness run count inconsistent with its own grid")
    require(matrix["total_runs"] == expected_main + expected_robust, "total run count inconsistent")
    require(main["latency_points"] == len(EXPECTED_LATENCY_GRID), "main grid inconsistent with latency sweep")
    require(main["seeds"] == len(EXPECTED_SEEDS), "main grid inconsistent with seed policy")

    exclusions = data["exclusions_and_failures"]
    require(exclusions["post_hoc_exclusion_permitted"] is False, "post-hoc exclusion cannot be permitted")
    for key in ("empty_book_runs_retained", "timeout_runs_retained", "degenerate_runs_retained"):
        require(exclusions[key] is True, f"retention guarantee weakened: {key}")
    require(exclusions["minimum_retained_failure_runs_reported"] >= 3, "retained failure-run floor lowered")

    negative = data["negative_result_criteria"]
    require(REQUIRED_NEGATIVE_CRITERIA.issubset(set(negative)), "negative-result criterion removed")
    require(negative["negative_result_is_a_valid_completion"] is True, "negative result must remain a valid completion")

    reporting = data["reporting"]
    require(
        REQUIRED_PROHIBITED_CLAIMS.issubset(set(reporting["prohibited"])),
        "prohibited-claim boundary weakened",
    )
    require(len(reporting["required"]) >= 6, "required reporting list truncated")

    boundary = str(data["claim_boundary"]).lower()
    require("synthetic simulation only" in boundary, "claim boundary must declare synthetic-only scope")
    for phrase in ("real-market performance", "realized returns", "exchange deployability"):
        require(phrase in boundary, f"claim boundary safeguard missing: {phrase}")

    require(doc_path.is_file(), "protocol document missing")
    text = doc_path.read_text(encoding="utf-8").lower()
    for phrase in PROTOCOL_SAFEGUARDS:
        require(phrase in text, f"protocol safeguard missing: {phrase}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", nargs="?", type=Path, default=CONTRACT)
    args = parser.parse_args()
    data = json.loads(args.contract.read_text(encoding="utf-8"))
    validate(data, args.contract.parent / "PROTOCOL.md")
    print("PASS: microstructure mechanism contract is frozen, two-mechanism, pre-result and claim-bounded")


if __name__ == "__main__":
    main()
