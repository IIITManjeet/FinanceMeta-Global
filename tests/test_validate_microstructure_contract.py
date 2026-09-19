"""Regression tests for the market-microstructure mechanism contract validator."""

from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_microstructure_contract.py"
CONTRACT = ROOT / "evaluation/microstructure-mechanism-2026-09/experiment_contract.json"
PROTOCOL = ROOT / "evaluation/microstructure-mechanism-2026-09/PROTOCOL.md"

def _primary(data: dict, metric_id: str) -> dict:
    return next(entry for entry in data["metrics"]["primary"] if entry["id"] == metric_id)


spec = importlib.util.spec_from_file_location("validator", SCRIPT)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


class MicrostructureMechanismContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def _reject(self, mutate) -> None:
        mutated = copy.deepcopy(self.data)
        mutate(mutated)
        with self.assertRaises(AssertionError):
            validator.validate(mutated, PROTOCOL)

    def test_current_contract_passes(self) -> None:
        validator.validate(self.data, PROTOCOL)

    def test_contract_id_cannot_drift(self) -> None:
        self._reject(lambda d: d.__setitem__("contract_id", "FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v3"))

    def test_status_cannot_leave_frozen_pre_result(self) -> None:
        self._reject(lambda d: d.__setitem__("status", "EXECUTED"))

    def test_results_cannot_be_marked_inspected_before_the_run(self) -> None:
        self._reject(lambda d: d["freeze"].__setitem__("results_inspected", True))

    def test_simulator_cannot_predate_the_brief_freeze(self) -> None:
        self._reject(lambda d: d["freeze"].__setitem__("simulator_implemented_at_freeze", True))

    def test_post_result_parameter_change_cannot_be_permitted(self) -> None:
        self._reject(lambda d: d["freeze"].__setitem__("parameters_may_change_after_results", True))

    def test_third_mechanism_cannot_be_admitted_after_results(self) -> None:
        self._reject(lambda d: d["freeze"].__setitem__("third_mechanism_may_be_added_after_results", True))

    def test_mechanism_count_cannot_exceed_two(self) -> None:
        self._reject(lambda d: d["mechanisms"].__setitem__("count", 3))

    def test_mechanism_pair_cannot_be_swapped(self) -> None:
        self._reject(lambda d: d["mechanisms"]["B"].__setitem__("id", "FREQUENT_BATCH_AUCTION"))

    def test_builder_attribution_cannot_be_removed(self) -> None:
        self._reject(lambda d: d["authority"].__setitem__("builder", "FinanceMeta"))

    def test_order_flow_state_independence_cannot_be_disabled(self) -> None:
        self._reject(lambda d: d["order_flow"].__setitem__("state_independent", False))

    def test_seeds_cannot_be_trimmed(self) -> None:
        self._reject(lambda d: d["seed_policy"].__setitem__("seeds", list(range(10))))

    def test_failed_seeds_cannot_be_discarded(self) -> None:
        self._reject(lambda d: d["seed_policy"].__setitem__("failed_seeds_may_be_discarded", True))

    def test_latency_sweep_cannot_be_extended_after_freeze(self) -> None:
        self._reject(lambda d: d["latency"].__setitem__("tracked_agent_one_way_ms", [0, 1, 2, 5, 10, 25, 50, 100, 250]))

    def test_matched_baseline_cannot_move_off_the_swept_grid(self) -> None:
        self._reject(lambda d: d["latency"].__setitem__("matched_baseline_ms", 7))

    def test_fees_cannot_be_introduced_after_freeze(self) -> None:
        self._reject(lambda d: d["fees"].__setitem__("maker_bps", -0.2))

    def test_primary_metric_cannot_be_dropped(self) -> None:
        self._reject(lambda d: d["metrics"].__setitem__("primary", d["metrics"]["primary"][:4]))

    def test_decision_metric_cannot_be_swapped_for_a_better_looking_one(self) -> None:
        self._reject(lambda d: d["metrics"]["decision_metric"].__setitem__("id", "fill_probability"))

    def test_decision_comparison_point_cannot_move(self) -> None:
        self._reject(lambda d: d["metrics"]["decision_metric"].__setitem__("compared_at_latency_ms", 100))

    def test_means_only_reporting_cannot_be_enabled(self) -> None:
        self._reject(lambda d: d["metrics"].__setitem__("means_only_reporting_permitted", True))

    def test_required_control_cannot_be_removed(self) -> None:
        self._reject(lambda d: d["controls"].pop("identity_run"))

    def test_analytic_sanity_allocation_cannot_drift(self) -> None:
        self._reject(
            lambda d: d["controls"]["analytic_sanity_case"].__setitem__(
                "expected_pro_rata_allocation_lots", {"X": 2, "Y": 4}
            )
        )

    def test_second_robustness_cell_cannot_be_added(self) -> None:
        self._reject(lambda d: d["robustness_cell"].__setitem__("count", 2))

    def test_run_matrix_must_stay_internally_consistent(self) -> None:
        self._reject(lambda d: d["run_matrix"]["main"].__setitem__("runs", 240))

    def test_total_run_count_must_match_its_parts(self) -> None:
        self._reject(lambda d: d["run_matrix"].__setitem__("total_runs", 480))

    def test_post_hoc_exclusion_cannot_be_permitted(self) -> None:
        self._reject(lambda d: d["exclusions_and_failures"].__setitem__("post_hoc_exclusion_permitted", True))

    def test_degenerate_run_retention_cannot_be_weakened(self) -> None:
        self._reject(lambda d: d["exclusions_and_failures"].__setitem__("degenerate_runs_retained", False))

    def test_negative_result_cannot_be_demoted_from_valid_completion(self) -> None:
        self._reject(lambda d: d["negative_result_criteria"].__setitem__("negative_result_is_a_valid_completion", False))

    def test_negative_result_criterion_cannot_be_removed(self) -> None:
        self._reject(lambda d: d["negative_result_criteria"].pop("LATENCY_DRIVEN"))

    def test_prohibited_claim_cannot_be_removed(self) -> None:
        self._reject(
            lambda d: d["reporting"].__setitem__(
                "prohibited", [c for c in d["reporting"]["prohibited"] if c != "real-market alpha"]
            )
        )

    def test_claim_boundary_cannot_drop_synthetic_scope(self) -> None:
        self._reject(lambda d: d.__setitem__("claim_boundary", "Results hold generally across venues."))

    def test_freeze_sha_must_not_be_embedded(self) -> None:
        """A commit cannot contain its own hash; identity comes from tag + PR head + CI artifact."""
        self._reject(
            lambda d: d["authority"].__setitem__(
                "freeze_commit_sha", "5bb5adab2749e1d3e5f4e29d027333df7f8f43eb"
            )
        )

    def test_authoritative_repository_cannot_drift(self) -> None:
        self._reject(lambda d: d["authority"].__setitem__("repository_url", "https://example.invalid/repo"))

    def test_amendment_log_cannot_be_emptied(self) -> None:
        self._reject(lambda d: d["freeze"].__setitem__("amendments", []))

    def test_amendment_cannot_be_made_after_frozen_scale_outcomes(self) -> None:
        self._reject(
            lambda d: d["freeze"]["amendments"][0]["outcomes_seen_before_change"].__setitem__(
                "frozen_scale", True
            )
        )

    def test_amendment_must_retain_the_superseded_rule(self) -> None:
        self._reject(lambda d: d["freeze"]["amendments"][0].__setitem__("old_rule", ""))

    def test_amendment_cannot_drop_its_reviewer_reference(self) -> None:
        self._reject(lambda d: d["freeze"]["amendments"][0].pop("reviewer_reference"))

    def test_decision_metric_cannot_drop_the_unfilled_remainder(self) -> None:
        self._reject(
            lambda d: _primary(d, "implementation_shortfall_bps").__setitem__(
                "includes_unfilled_remainder", False
            )
        )

    def test_decision_metric_must_stay_defined_for_zero_fill_runs(self) -> None:
        self._reject(
            lambda d: _primary(d, "implementation_shortfall_bps").__setitem__(
                "defined_for_zero_fill_runs", False
            )
        )

    def test_reference_mid_fallback_cannot_be_removed(self) -> None:
        self._reject(
            lambda d: _primary(d, "implementation_shortfall_bps").__setitem__(
                "reference_mid_rule", "the mid at the horizon end"
            )
        )

    def test_inference_cannot_stop_being_paired(self) -> None:
        self._reject(lambda d: d["metrics"]["decision_metric"].__setitem__("pairing", "unpaired"))

    def test_independent_arm_resampling_cannot_be_permitted(self) -> None:
        self._reject(
            lambda d: d["metrics"]["decision_metric"].__setitem__(
                "independent_arm_resampling_permitted", True
            )
        )

    def test_cancel_schema_cannot_revert_to_state_resampling(self) -> None:
        self._reject(
            lambda d: d["order_flow"]["event_schema"].__setitem__(
                "cancel_target", "a uniform draw resolved against the current resting orders"
            )
        )

    def test_cancels_cannot_be_aimed_at_the_tracked_agent(self) -> None:
        self._reject(
            lambda d: d["order_flow"]["event_schema"].__setitem__("cancel_targets_tracked_orders", True)
        )

    def test_limit_price_reference_must_stay_explicit(self) -> None:
        self._reject(
            lambda d: d["order_flow"]["event_schema"].__setitem__("limit_price", "drawn near the touch")
        )

    def test_zero_latency_control_cannot_reclaim_all_agents(self) -> None:
        self._reject(
            lambda d: d["controls"]["zero_latency_control"].__setitem__(
                "description", "All agents at 0 ms one-way latency."
            )
        )

    def test_zero_latency_control_cannot_claim_a_distinct_cell(self) -> None:
        self._reject(lambda d: d["controls"]["zero_latency_control"].__setitem__("distinct_cell", True))

    def test_unstable_threshold_cannot_be_loosened(self) -> None:
        self._reject(
            lambda d: d["negative_result_criteria"]["UNSTABLE"].__setitem__(
                "implied_for_30_nonzero_pairs", "minority sign count at least 2"
            )
        )

    def test_unstable_cannot_become_unconditional(self) -> None:
        self._reject(
            lambda d: d["negative_result_criteria"]["UNSTABLE"].__setitem__("conditional_on_non_null", False)
        )

    def test_attenuation_ratio_cannot_drift(self) -> None:
        self._reject(
            lambda d: d["negative_result_criteria"]["LATENCY_DRIVEN"].__setitem__("attenuation_ratio_max", 0.95)
        )

    def test_reporting_precedence_cannot_be_reordered(self) -> None:
        self._reject(
            lambda d: d["negative_result_criteria"].__setitem__(
                "precedence",
                ["DIFFERENCE_DETECTED", "NULL", "UNSTABLE", "LATENCY_DRIVEN", "ASSUMPTION_DRIVEN"],
            )
        )

    def test_robustness_rationale_cannot_reclaim_fifo_degeneration(self) -> None:
        self._reject(
            lambda d: d["robustness_cell"].__setitem__("assumption_removed", "pro_rata_reduces_to_fifo")
        )

    def test_tracked_display_cannot_change_inside_the_robustness_cell(self) -> None:
        self._reject(lambda d: d["robustness_cell"].__setitem__("tracked_display_lots_in_cell", 1))

    def test_initial_ladder_cannot_drift(self) -> None:
        self._reject(lambda d: d["initial_book_state"]["ladder"].__setitem__("bid_prices", [998, 997, 996, 995, 994]))

    def test_initial_ladder_must_stay_consistent_with_the_mid(self) -> None:
        self._reject(lambda d: d["initial_book_state"]["ladder"].__setitem__("best_bid", 990))

    def test_queue_measures_cannot_become_comparable(self) -> None:
        self._reject(
            lambda d: _primary(d, "queue_and_wait")["comparability"].__setitem__(
                "queue_measure", "directly comparable across mechanisms"
            )
        )

    def test_pro_rata_under_allocation_examples_cannot_be_removed(self) -> None:
        self._reject(lambda d: d["mechanisms"]["B"].__setitem__("under_allocation_worked_examples", []))

    def test_min_allocation_cannot_become_a_guarantee(self) -> None:
        self._reject(
            lambda d: d["mechanisms"]["B"].__setitem__(
                "min_allocation_semantics", "every resting order is guaranteed one lot"
            )
        )

    def test_missing_protocol_document_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AssertionError):
                validator.validate(copy.deepcopy(self.data), Path(tmp) / "PROTOCOL.md")

    def test_protocol_without_safeguards_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "PROTOCOL.md"
            stub.write_text("# protocol\n\nnothing declared here\n", encoding="utf-8")
            with self.assertRaises(AssertionError):
                validator.validate(copy.deepcopy(self.data), stub)


if __name__ == "__main__":
    unittest.main()
