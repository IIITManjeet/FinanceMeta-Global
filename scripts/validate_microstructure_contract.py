#!/usr/bin/env python3
"""Fail-closed validator for the FinanceMeta market-microstructure mechanism contract."""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "evaluation/microstructure-mechanism-2026-09/experiment_contract.json"
PROTOCOL_DOC = ROOT / "evaluation/microstructure-mechanism-2026-09/PROTOCOL.md"

CONTRACT_ID = "FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v8"
FROZEN_DATE = "2026-09-19"
AMENDED_DATE = "2026-09-23"
EXPECTED_STATUS = "PARTIALLY_UNBLINDED_DEVELOPMENT_EXPOSED"
EXPECTED_CONFIRMATORY_STATUS = "NOT_AUTHORIZED_PENDING_INDEPENDENT_PRE_RUN_REVIEW"
EXPECTED_UNSTABLE_ALPHA = 0.05
EXPECTED_INTERVAL_ALPHA = 0.05
EXPECTED_PREDICATE_KIND = "exact_boolean_true"
REQUIRED_AUTHORIZATION_KEYS = {
    "mechanism", "receipt_file", "predicate", "predicate_kind", "receipt_must_name",
    "reviewed_sha_rule", "receipt_is_the_only_post_review_mutable_input", "run_records",
}
EXPECTED_CONFIRMATION_SEEDS = list(range(100, 130))
EXPOSED_DEVELOPMENT_SEEDS = [0, 1, 2, 3, 4, 5, 7, 11]
EXPECTED_FREEZE_TAG = "microstructure-freeze-v8"
EXPECTED_SUPERSEDED_TAGS = [f"microstructure-freeze-v{i}" for i in range(1, 8)]
PREVIOUS_FREEZE_TAG = EXPECTED_SUPERSEDED_TAGS[-1]
EXPECTED_WARM_UP = 10000
EXPECTED_HORIZON = 100000
EXPECTED_PARENT_LOTS = 500
EXPECTED_DISPLAY_LOTS = 10
EXPECTED_BOOTSTRAP_SEED = 424242
REQUIRED_DEFECT_IDS = {f"D{i}" for i in range(1, 55)}
# The narrative must group amendments, not wave at them.
MAX_SUMMARY_SPAN = 20
REQUIRED_RUN_FIELDS = {
    "mechanism", "seed", "latency_ms", "cell",
    "fill_probability", "implementation_shortfall_bps", "spread_at_execution_ticks",
    "time_to_first_fill_ms", "time_to_full_fill_ms", "queue_measure", "price_impact_bps",
    "filled_lots", "parent_lots", "arrival_mid", "final_mid", "placements",
    "limit_no_ops", "cancel_no_ops", "market_no_ops", "flags",
    "stream_sha256", "record_sha256",
}
EXPECTED_FLOW_RATES = {"limit_order_rate_per_level_per_sec": 1.2, "market_order_rate_per_side_per_sec": 0.9,
                       "cancel_rate_per_resting_lot_per_sec": 0.14, "levels_from_opposite_best": 5}
EXPECTED_SIZE_DISTRIBUTION = {"1": 0.5, "2": 0.25, "5": 0.15, "10": 0.1}
EXPECTED_ROBUSTNESS_SIZE_DISTRIBUTION = {"1": 1.0}
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
    "partially unblinded",
    "confirmation seed",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@functools.lru_cache(maxsize=None)
def _previous_freeze(tag: str) -> dict:
    """The contract as committed at the previous freeze tag.

    The append-only property of the logs used to live in git history alone;
    the validator only checked that ids were contiguous, so deleting an entry
    and renumbering the rest passed. Comparing against the tagged blob makes
    the property mechanical. If the tag cannot be read this fails, because a
    clone without tags cannot vouch for the logs.
    """
    rel = CONTRACT.relative_to(ROOT).as_posix()
    try:
        done = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"refs/tags/{tag}:{rel}"], capture_output=True, check=False
        )
    except OSError as exc:
        raise AssertionError(f"cannot run git to read the contract at {tag}: {exc}")
    require(done.returncode == 0, f"cannot read the contract at {tag}: the append-only check needs the previous freeze tag")
    return json.loads(done.stdout.decode("utf-8"))


def _validate_exposure(freeze: dict) -> None:
    """The recorded exposure is retained, not quietly reverted."""
    exposure = freeze["exposure"]
    require(exposure["occurred"] is True, "the recorded exposure cannot be erased")
    require(
        exposure["scope"]["seeds_exposed"] == EXPOSED_DEVELOPMENT_SEEDS,
        "exposed seed list drift",
    )
    require(exposure["evidence"]["preserved"] is True, "exposure evidence must remain preserved")
    require(
        str(exposure["tuning_in_response"]).lower().startswith("none"),
        "nothing may be tuned in response to the exposed verdict",
    )
    require(
        exposure["must_be_reported_in_findings"] is True,
        "the exposure must remain reportable in the findings record",
    )


def _validate_defects(freeze: dict, previous: dict) -> None:
    """Implementation defects found pre-run are declared, not quietly fixed."""
    defects = freeze["implementation_defects_corrected"]
    ids = [entry["id"] for entry in defects]
    require(REQUIRED_DEFECT_IDS.issubset(set(ids)), "a declared implementation defect was removed")
    for entry in defects:
        for key in ("defect", "fix", "verified", "severity", "found_by"):
            require(str(entry.get(key, "")).strip() != "", f"defect {entry['id']} missing {key}")
    # A defect's fix or verification may be corrected, as D2's was when a
    # disclosed figure proved unreproducible, but what the defect was, and its
    # place in the list, cannot change once tagged.
    before = [(e["id"], e["defect"]) for e in previous["freeze"]["implementation_defects_corrected"]]
    now = [(e["id"], e["defect"]) for e in defects]
    require(now[: len(before)] == before,
            f"defect log must extend the entries recorded at {PREVIOUS_FREEZE_TAG}: none may be dropped, renumbered or rewritten")


def _validate_amendments(freeze: dict, previous: dict) -> None:
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
        require(
            re.fullmatch(r"[0-9a-f]{7,40}", str(entry["superseded_commit"])) is not None,
            f"amendment {entry['id']} superseded_commit must be a commit hash",
        )
    ids = [entry["id"] for entry in amendments]
    require(
        ids == [f"A{i}" for i in range(1, len(ids) + 1)],
        "amendment log must stay append-only and contiguously numbered",
    )
    before = previous["freeze"]["amendments"]
    require(
        amendments[: len(before)] == before,
        f"amendment log must extend the log recorded at {PREVIOUS_FREEZE_TAG} exactly: "
        "no entry may be changed, reordered or dropped",
    )


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
    require(decision["interval_alpha"] == EXPECTED_INTERVAL_ALPHA, "decision interval alpha drift")
    level = round(100 * (1 - decision["interval_alpha"]))
    require(f"{level} percent" in decision["interval"], "interval prose disagrees with interval_alpha")


def _validate_authorization(data: dict) -> None:
    """Authorisation lives outside this document, so granting it never edits it."""
    require("authorization" in data, "authorization block missing: nothing would gate the run")
    auth = data["authorization"]
    require(REQUIRED_AUTHORIZATION_KEYS.issubset(set(auth)), "authorization block incomplete")
    require(
        auth["receipt_is_the_only_post_review_mutable_input"] is True,
        "the receipt must remain the only input that may change after review",
    )
    # The kind is what is pinned; the prose is a description and could be made
    # to contain any phrase while describing the opposite.
    require(auth["predicate_kind"] == EXPECTED_PREDICATE_KIND, "authorisation predicate must be an exact boolean")
    require(str(auth["predicate"]).strip() != "", "authorisation predicate description missing")
    rule = auth["reviewed_sha_rule"]
    require("40-character SHA" in rule, "the receipt must name a full reviewed SHA")
    require("HEAD exactly" in rule and "ancestor is not accepted" in rule,
            "the reviewed SHA must be the executing revision, not an ancestor of it")
    require("refs/tags/" in rule and "exactly the named SHA" in rule,
            "the tag must resolve as a tag to the SHA in the receipt")
    require("authority.freeze_tag" in rule, "the reviewed tag must be the freeze tag")
    require("clean" in rule and "byte-identical" in rule,
            "the gate must require a clean tree and a byte-identical contract")
    for key in ("approved", "contract_id", "reviewed_sha", "reviewed_tag"):
        require(key in auth["receipt_must_name"], f"receipt must name {key}")
    require(
        data["confirmatory_status"] == EXPECTED_CONFIRMATORY_STATUS,
        "confirmatory_status is frozen; authorisation is granted by the receipt, not by editing it",
    )


def _validate_negative_criteria(negative: dict) -> None:
    require(REQUIRED_NEGATIVE_CRITERIA.issubset(set(negative)), "negative-result criterion removed")
    require(negative["negative_result_is_a_valid_completion"] is True, "negative result must remain a valid completion")
    require(negative["overlap_permitted"] is True, "label overlap must remain declared")
    require(negative["precedence"] == EXPECTED_PRECEDENCE, "reporting precedence drift")

    unstable = negative["UNSTABLE"]
    require(unstable["alpha"] == EXPECTED_UNSTABLE_ALPHA, "UNSTABLE significance level drift")
    require(unstable["implied_for_30_nonzero_pairs"] == UNSTABLE_MIN_MINORITY, "UNSTABLE threshold loosened")
    require(unstable["single_opposite_seed_triggers"] is False, "a single opposite seed cannot trigger UNSTABLE")
    require(unstable["conditional_on_non_null"] is True, "UNSTABLE must stay conditional on NULL not holding")

    for label in ("LATENCY_DRIVEN", "ASSUMPTION_DRIVEN"):
        require(
            negative[label]["attenuation_ratio_max"] == ATTENUATION_RATIO_MAX,
            f"{label} attenuation ratio drift",
        )


COUNT_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
    9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty",
}


def _covered_by_a_range(amendment_id: str, text: str) -> bool:
    """Whether a narrative names this amendment, on its own or inside a range.

    The summaries are written as ranges such as A25-A35, so an amendment is
    covered when it is named outright or falls inside one of them.
    """
    number = int(amendment_id[1:])
    if re.search(rf"\b{amendment_id}\b", text):
        return True
    for low, high in re.findall(r"\bA(\d+)\s*[-\u2013]\s*A?(\d+)\b", text):
        # A range wide enough to swallow the whole log is not a summary. One
        # line reading A1-A61 would otherwise satisfy this for every amendment
        # at once, which is the vacuous check the findings drift came from.
        if int(high) - int(low) >= MAX_SUMMARY_SPAN:
            continue
        if int(low) <= number <= int(high):
            return True
    return False


def validate(data: dict[str, object], doc_path: Path = PROTOCOL_DOC) -> None:
    require(data.get("contract_id") == CONTRACT_ID, "contract ID drift")
    require(data.get("status") == EXPECTED_STATUS, "exposure status must not be downgraded")
    require(
        data.get("confirmatory_status") == EXPECTED_CONFIRMATORY_STATUS,
        "confirmatory run cannot be marked authorised here",
    )
    require(data.get("frozen_date") == FROZEN_DATE, "freeze date drift")
    require(data.get("amended_date") == AMENDED_DATE, "amended date drift")
    require(dt.date.fromisoformat(AMENDED_DATE) >= dt.date.fromisoformat(FROZEN_DATE), "amended before frozen")

    authority = data["authority"]
    require(authority["builder"] == "Manjeet Pathak", "builder attribution removed or altered")
    require(authority["repository_url"] == EXPECTED_REPOSITORY_URL, "authoritative repository drift")
    require(authority["freeze_tag"] == EXPECTED_FREEZE_TAG, "freeze tag drift")
    require(authority["superseded_tags"] == EXPECTED_SUPERSEDED_TAGS, "superseded tag list drift")
    require(authority["freeze_tag"] not in authority["superseded_tags"], "the current tag cannot supersede itself")
    previous = _previous_freeze(PREVIOUS_FREEZE_TAG)
    require(authority["freeze_commit_sha"] is None, "a self-referential freeze SHA cannot be embedded")
    require("freeze_identity_rule" in authority, "freeze identity rule missing")

    freeze = data["freeze"]
    require(
        freeze["results_inspected"] is True,
        "results_inspected must stay true while the recorded exposure stands",
    )
    _validate_exposure(freeze)
    _validate_defects(freeze, previous)
    require(freeze["simulator_implemented_at_freeze"] is False, "simulator must not exist at brief freeze")
    require(freeze["parameters_may_change_after_results"] is False, "post-result parameter change cannot be permitted")
    require(
        freeze["third_mechanism_may_be_added_after_results"] is False,
        "a third mechanism cannot be admitted after results",
    )
    _validate_amendments(freeze, previous)

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
    require(seeds["confirmation_seeds"] == EXPECTED_CONFIRMATION_SEEDS, "confirmation seed set drift")
    require(len(seeds["confirmation_seeds"]) == len(EXPECTED_SEEDS), "confirmation seed count must match")
    require(
        not (set(seeds["confirmation_seeds"]) & set(seeds["development_seeds"])),
        "confirmation seeds must stay disjoint from the exposed development seeds",
    )
    require(
        seeds["confirmation_seeds_frozen_before_any_further_outcome_access"] is True,
        "confirmation seeds must remain pre-registered",
    )
    require(seeds["confirmatory_run_uses"] == "confirmation_seeds", "confirmatory run must use the disjoint set")

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

    require(book["warm_up_events_discarded"] == EXPECTED_WARM_UP, "warm-up scale drift")
    require(
        data["horizon"]["events_per_run_after_warm_up"] == EXPECTED_HORIZON,
        "frozen horizon drift: reduced scale is what caused the recorded exposure",
    )
    tracked = data["participants"]["tracked_agent"]
    require(tracked["parent_quantity_lots"] == EXPECTED_PARENT_LOTS, "parent quantity drift")
    require(tracked["display_lots"] == EXPECTED_DISPLAY_LOTS, "display size drift")
    require("cancel and replace" in tracked["replenishment"], "replenishment semantics drift")
    for key, value in EXPECTED_FLOW_RATES.items():
        require(flow[key] == value, f"order-flow rate drift: {key}")
    require(flow["order_size_distribution_lots"] == EXPECTED_SIZE_DISTRIBUTION, "order size distribution drift")
    require(seeds["bootstrap_seed"] == EXPECTED_BOOTSTRAP_SEED, "bootstrap seed drift")

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
    identity_scope = controls["identity_run"]["verification"].lower()
    require("sentinel" in identity_scope, "pre-run identity control must stay on sentinel seeds")
    require("executed" in identity_scope, "identity must be asserted over the executed run matrix")

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
    require(
        robustness["order_size_distribution_lots"] == EXPECTED_ROBUSTNESS_SIZE_DISTRIBUTION,
        "robustness cell size distribution drift",
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
    _validate_authorization(data)

    reporting = data["reporting"]
    require(
        REQUIRED_PROHIBITED_CLAIMS.issubset(set(reporting["prohibited"])),
        "prohibited-claim boundary weakened",
    )
    require(len(reporting["required"]) >= 6, "required reporting list truncated")

    lock = data["reproduction"]["environment_lock"]
    require(isinstance(lock, dict), "environment lock must be frozen, not null")
    require(lock["hash_enforced"] is True, "environment lock must enforce hashes")
    require(lock["frozen_before_confirmatory_run"] is True, "lock must predate the confirmatory run")
    require(lock["build_backend_pinned"] is True, "the build backend must stay pinned")
    require(lock["sdist_fallback_possible"] is False, "every pin must carry a wheel hash")
    require("--no-build-isolation" in lock["install_command"], "install must not re-fetch the backend")
    require(lock["sdist_hashes_present"] is False, "an sdist hash would permit an unpinned source build")
    require(lock["installed_environment_verified_before_run"] is True,
            "the gate must check site-packages, not only the lock file")
    require("receipt" in lock["verified_before_run"], "the run must be gated on the authorisation receipt")
    require("confirmatory_status" not in lock["verified_before_run"],
            "confirmatory_status is read by no code and cannot be described as the gate")
    lock_path = ROOT / lock["file"]
    require(lock_path.is_file(), "environment lock file missing")
    actual = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    require(
        actual == lock["sha256"],
        f"environment lock digest does not match the file: contract {lock['sha256']}, file {actual}",
    )

    # The data contract listed the per-run fields in prose, and a required one
    # went undelivered from the freeze because nothing compared the list with
    # what the record carries.
    declared = set(data["reporting"]["required_run_fields"])
    require(REQUIRED_RUN_FIELDS.issubset(declared),
            f"required run fields dropped: {', '.join(sorted(REQUIRED_RUN_FIELDS - declared))}")
    require("record_sha256" in declared, "the run record must carry a digest of itself")
    artifacts = set(data["reporting"]["artifacts"])
    for name in ("comparison.md", "latency_sensitivity.svg", "runs.jsonl", "decision.json"):
        require(name in artifacts, f"the run must emit {name}")
    require("stream_sha256" in declared, "the run record must carry the intent-stream digest")

    boundary = str(data["claim_boundary"]).lower()
    require("synthetic simulation only" in boundary, "claim boundary must declare synthetic-only scope")
    for phrase in ("real-market performance", "realized returns", "exchange deployability"):
        require(phrase in boundary, f"claim boundary safeguard missing: {phrase}")

    brief = doc_path.parent / "brief.md"
    require(brief.is_file(), "builder brief missing")
    brief_text_raw = brief.read_text(encoding="utf-8")
    brief_text = brief_text_raw.lower()
    require("100-129" in brief_text, "brief must name the confirmation seed set")
    require(
        "seeds 0-29" not in brief_text.replace("development seeds 0-29", ""),
        "brief must not present the exposed development seeds as the evaluation set",
    )

    require(doc_path.is_file(), "protocol document missing")
    text = doc_path.read_text(encoding="utf-8").lower()
    for phrase in PROTOCOL_SAFEGUARDS:
        require(phrase in text, f"protocol safeguard missing: {phrase}")

    for doc, doc_text in ((brief, brief_text), (doc_path, text)):
        stated = re.search(r"amended (\d{4}-\d{2}-\d{2})", doc_text)
        require(stated is not None, f"{doc.name} must state the amended date")
        require(stated.group(1) == data["amended_date"],
                f"{doc.name} says amended {stated.group(1)}, the contract says {data['amended_date']}")

    # Nothing used to read the findings document, so its narrative drifted from
    # the contract twice without failing anything: the amendment summary skipped
    # a run of entries and two defects had no entry at all.
    findings = doc_path.parent / "FINDINGS.md"
    require(findings.is_file(), "findings document missing")
    findings_text = findings.read_text(encoding="utf-8")
    missing = [
        entry["id"] for entry in data["freeze"]["implementation_defects_corrected"]
        if not re.search(rf"\b{entry['id']}\b", findings_text)
    ]
    require(not missing, f"FINDINGS.md does not account for {', '.join(missing)}")

    # Only the narrative section counts. The header names the whole span, A1 to
    # the latest, which would make a per-amendment check vacuous.
    section = re.search(r"\n## Amendments after freeze\n(.*?)(?=\n## |\Z)", brief_text_raw, re.S)
    require(section is not None, "brief.md must carry the amendments narrative")
    narrative = re.sub(r"\(A\d+-A\d+\)", "", section.group(1))
    gaps = [
        amendment["id"] for amendment in data["freeze"]["amendments"]
        if not _covered_by_a_range(amendment["id"], narrative)
    ]
    require(not gaps, f"the brief's amendment narrative does not cover {', '.join(gaps)}")

    # The prose count of invalidating defects and the severity fields are two
    # statements of one fact, and they drifted apart the moment a defect was
    # added without touching the sentence.
    invalidating = [
        entry["id"] for entry in data["freeze"]["implementation_defects_corrected"]
        if entry["severity"] == "invalidating"
    ]
    word = COUNT_WORDS.get(len(invalidating))
    require(word is not None, f"{len(invalidating)} invalidating defects is outside the counted range")
    for doc, doc_text in ((findings, findings_text), (brief, brief_text_raw)):
        stated = re.search(r"\b(\w+) of them(?: \(| would have invalidated)", doc_text)
        require(stated is not None, f"{doc.name} must state how many defects were invalidating")
        require(stated.group(1).lower() == word,
                f"{doc.name} says {stated.group(1).lower()} invalidating, the contract marks {word}")
    for entry_id in invalidating:
        require(re.search(rf"\b{entry_id}\b", findings_text) is not None,
                f"FINDINGS.md does not name invalidating defect {entry_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", nargs="?", type=Path, default=CONTRACT)
    args = parser.parse_args()
    data = json.loads(args.contract.read_text(encoding="utf-8"))
    validate(data, args.contract.parent / "PROTOCOL.md")
    print("PASS: contract is two-mechanism, exposure-declared, confirmation-seeded and claim-bounded")


if __name__ == "__main__":
    main()
