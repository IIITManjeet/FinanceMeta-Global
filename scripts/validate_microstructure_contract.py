#!/usr/bin/env python3
"""Fail-closed validator for the FinanceMeta market-microstructure mechanism contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "evaluation/microstructure-mechanism-2026-09/experiment_contract.json"
PROTOCOL_DOC = ROOT / "evaluation/microstructure-mechanism-2026-09/PROTOCOL.md"

CONTRACT_ID = "FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v2"
FROZEN_DATE = "2026-09-19"
EXPECTED_REPOSITORY_URL = "https://github.com/build-the-future-11/FinanceMeta-Global"

EXPECTED_MECHANISM_IDS = {"FIFO", "PRO_RATA"}
EXPECTED_SEEDS = list(range(30))
EXPECTED_LATENCY_GRID = [0, 1, 2, 5, 10, 25, 50, 100]
MATCHED_BASELINE_MS = 5

EXPECTED_BID_LADDER = [999, 998, 997, 996, 995]
EXPECTED_ASK_LADDER = [1001, 1002, 1003, 1004, 1005]

UNSTABLE_MIN_MINORITY = "minority sign count at least 10"
ATTENUATION_RATIO_MAX = 0.5
EXPECTED_PRECEDENCE = ["NULL", "UNSTABLE", "LATENCY_DRIVEN", "ASSUMPTION_DRIVEN", "DIFFERENCE_DETECTED"]

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

REQUIRED_AMENDMENT_KEYS = {
    "id",
    "timestamp_utc",
    "section",
    "old_rule",
    "new_rule",
    "reason",
    "reviewer_reference",
    "outcomes_seen_before_change",
    "superseded_commit",
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
    "paired by seed",
    "opportunity cost",
    "no dynamic effect",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _validate_amendments(freeze: dict) -> None:
    amendments = freeze["amendments"]
    require(isinstance(amendments, list), "amendment log must be a list")
    require(len(amendments) >= 1, "amendment log cannot be emptied once the contract is amended")
    for entry in amendments:
        require(
            REQUIRED_AMENDMENT_KEYS.issubset(set(entry)),
            f"amendment entry missing required keys: {entry.get('id')}",
        )
        require(
            entry["outcomes_seen_before_change"]["frozen_scale"] is False,
            f"amendment {entry['id']} cannot be made after frozen-scale outcomes were seen",
        )
        require(str(entry["old_rule"]).strip() != "", f"amendment {entry['id']} must retain the old rule")


def _validate_event_schema(flow: dict) -> None:
    schema = flow["event_schema"]
    require(schema["cancel_targets_tracked_orders"] is False, "cancels must not target the tracked agent")
    require("target_intent_id" in schema["cancel_target"], "cancels must carry a fixed target intent id")
    require("counted no-op" in schema["cancel_target"], "an unmatched cancel must remain a counted no-op")
    require("book_relative" in schema["limit_price"], "limit price reference must stay explicit")
    require("intent_id" in schema["intent_id"], "limit intents must carry an immutable intent id")
    require("sha256" in schema["identity_hash_scope"], "identity hash scope must remain specified")


def _validate_decision_metric(metrics: dict) -> None:
    primary = {entry["id"]: entry for entry in metrics["primary"]}
    shortfall = primary["implementation_shortfall_bps"]
    require(shortfall["includes_unfilled_remainder"] is True, "decision metric must include the unfilled remainder")
    require(shortfall["defined_for_zero_fill_runs"] is True, "decision metric must be defined for zero-fill runs")
    require("opportunity cost" in shortfall["zero_fill_and_timeout_rule"], "zero-fill rule must be stated")
    require("carried forward" in shortfall["reference_mid_rule"], "reference mid fallback must be stated")
    require("frozen event count" in shortfall["horizon_rule"], "horizon must be the frozen event count")

    queue = primary["queue_and_wait"]
    require(
        queue["comparability"]["queue_measure"].startswith("descriptive_only"),
        "queue measures must remain descriptive only",
    )

    decision = metrics["decision_metric"]
    require(decision["id"] == "implementation_shortfall_bps", "decision metric drift")
    require(decision["direction"] == "lower_is_better", "decision metric direction drift")
    require(decision["compared_at_latency_ms"] == MATCHED_BASELINE_MS, "decision metric comparison point drift")
    require(decision["bootstrap_resamples"] == 10000, "bootstrap resample count drift")
    require(decision["pairing"] == "paired_by_seed", "inference must remain paired by seed")
    require(
        decision["independent_arm_resampling_permitted"] is False,
        "independent resampling of the two arms cannot be permitted",
    )
    require(decision["seed_pairs_required_complete"] is True, "seed pairs must remain complete")


def _validate_negative_criteria(negative: dict) -> None:
    require(REQUIRED_NEGATIVE_CRITERIA.issubset(set(negative)), "negative-result criterion removed")
    require(negative["negative_result_is_a_valid_completion"] is True, "negative result must remain a valid completion")
    require(negative["overlap_permitted"] is True, "label overlap must remain declared")
    require(negative["precedence"] == EXPECTED_PRECEDENCE, "reporting precedence drift")

    unstable = negative["UNSTABLE"]
    require(unstable["implied_for_30_nonzero_pairs"] == UNSTABLE_MIN_MINORITY, "UNSTABLE threshold loosened")
    require(unstable["single_opposite_seed_triggers"] is False, "a single opposite seed cannot trigger UNSTABLE")
    require(unstable["conditional_on_non_null"] is True, "UNSTABLE must stay conditional on NULL not holding")

    for label in ("LATENCY_DRIVEN", "ASSUMPTION_DRIVEN"):
        require(
            negative[label]["attenuation_ratio_max"] == ATTENUATION_RATIO_MAX,
            f"{label} attenuation ratio drift",
        )


def validate(data: dict[str, object], doc_path: Path = PROTOCOL_DOC) -> None:
    require(data.get("contract_id") == CONTRACT_ID, "contract ID drift")
    require(data.get("status") == "FROZEN_PRE_RESULT", "contract must remain frozen pre-result")
    require(data.get("frozen_date") == FROZEN_DATE, "freeze date drift")

    authority = data["authority"]
    require(authority["builder"] == "Manjeet Pathak", "builder attribution removed or altered")
    require(authority["repository_url"] == EXPECTED_REPOSITORY_URL, "authoritative repository drift")
    require(str(authority["freeze_tag"]).startswith("microstructure-freeze-v"), "freeze tag drift")
    require(authority["freeze_commit_sha"] is None, "a self-referential freeze SHA cannot be embedded")
    require("freeze_identity_rule" in authority, "freeze identity rule missing")

    freeze = data["freeze"]
    require(freeze["results_inspected"] is False, "results cannot be inspected before the main run")
    require(freeze["simulator_implemented_at_freeze"] is False, "simulator must not exist at brief freeze")
    require(freeze["parameters_may_change_after_results"] is False, "post-result parameter change cannot be permitted")
    require(
        freeze["third_mechanism_may_be_added_after_results"] is False,
        "a third mechanism cannot be admitted after results",
    )
    _validate_amendments(freeze)

    mechanisms = data["mechanisms"]
    require(mechanisms["count"] == 2, "exactly two mechanisms are permitted in the first pass")
    require(
        {mechanisms["A"]["id"], mechanisms["B"]["id"]} == EXPECTED_MECHANISM_IDS,
        "mechanism pair drift",
    )
    pro_rata = mechanisms["B"]
    require(pro_rata["min_allocation_lots"] == 1, "pro-rata minimum allocation drift")
    require(pro_rata["rounding"] == "largest_remainder", "pro-rata rounding rule drift")
    require(
        pro_rata["min_allocation_semantics"] == "participation floor, not a guaranteed allocation",
        "pro-rata minimum-allocation semantics drift",
    )
    require(len(pro_rata["under_allocation_worked_examples"]) >= 2, "under-allocation worked examples removed")

    flow = data["order_flow"]
    require(flow["state_independent"] is True, "order flow must remain state-independent")
    require(flow["generator"] == "zero_intelligence_poisson", "order-flow generator drift")
    _validate_event_schema(flow)

    seeds = data["seed_policy"]
    require(seeds["seeds"] == EXPECTED_SEEDS, "seed policy drift")
    require(seeds["seed_count"] == len(EXPECTED_SEEDS), "seed count inconsistent with seed list")
    require(seeds["failed_seeds_may_be_discarded"] is False, "failed seeds cannot be discarded")

    latency = data["latency"]
    require(latency["tracked_agent_one_way_ms"] == EXPECTED_LATENCY_GRID, "latency sweep drift")
    require(latency["matched_baseline_ms"] == MATCHED_BASELINE_MS, "matched-latency baseline drift")
    require(MATCHED_BASELINE_MS in EXPECTED_LATENCY_GRID, "matched baseline must lie on the swept grid")
    require(
        latency["background_latency_dynamic_effect"] == "none under the frozen non-reactive participant assumption",
        "background latency effect statement drift",
    )

    book = data["initial_book_state"]
    ladder = book["ladder"]
    require(ladder["bid_prices"] == EXPECTED_BID_LADDER, "initial bid ladder drift")
    require(ladder["ask_prices"] == EXPECTED_ASK_LADDER, "initial ask ladder drift")
    require(ladder["best_bid"] == book["mid_price"] - flow["tick_size"], "initial best bid inconsistent with mid")
    require(ladder["best_ask"] == book["mid_price"] + flow["tick_size"], "initial best ask inconsistent with mid")
    require(len(ladder["bid_prices"]) == book["levels_per_side"], "ladder inconsistent with levels per side")
    require(ladder["lots_per_price"] == book["lots_per_level"], "ladder inconsistent with lots per level")

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
    _validate_decision_metric(metrics)

    controls = data["controls"]
    require(set(controls) == REQUIRED_CONTROLS, "required control set drift")
    sanity = controls["analytic_sanity_case"]
    require(sanity["expected_fifo_allocation_lots"] == {"X": 2, "Y": 4}, "analytic FIFO allocation drift")
    require(sanity["expected_pro_rata_allocation_lots"] == {"X": 1, "Y": 5}, "analytic pro-rata allocation drift")
    zero_latency = controls["zero_latency_control"]
    require(
        "all agents" not in zero_latency["description"].lower(),
        "zero-latency control must not claim all agents at zero latency",
    )
    require(zero_latency["distinct_cell"] is False, "zero-latency control cell status drift")
    require("intent stream" in controls["identity_run"]["verification"], "identity control scope drift")

    robustness = data["robustness_cell"]
    require(robustness["count"] == 1, "exactly one prespecified robustness cell is permitted")
    require(robustness["id"] == "constant_order_size", "robustness cell drift")
    require(
        robustness["assumption_removed"] == "background_order_size_heterogeneity",
        "robustness cell must not reclaim a general pro-rata to price-time reduction",
    )
    require(
        robustness["tracked_display_lots_in_cell"] == data["participants"]["tracked_agent"]["display_lots"],
        "tracked display size must be unchanged in the robustness cell",
    )

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

    _validate_negative_criteria(data["negative_result_criteria"])

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
