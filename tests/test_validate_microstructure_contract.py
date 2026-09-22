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
        self._reject(lambda d: d.__setitem__("contract_id", "FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v9"))

    def test_status_cannot_leave_frozen_pre_result(self) -> None:
        self._reject(lambda d: d.__setitem__("status", "EXECUTED"))

    def test_recorded_exposure_cannot_be_walked_back(self) -> None:
        """results_inspected must stay true while the exposure record stands."""
        self._reject(lambda d: d["freeze"].__setitem__("results_inspected", False))

    def test_exposure_record_cannot_be_erased(self) -> None:
        self._reject(lambda d: d["freeze"]["exposure"].__setitem__("occurred", False))

    def test_exposed_seed_list_cannot_drift(self) -> None:
        self._reject(lambda d: d["freeze"]["exposure"]["scope"].__setitem__("seeds_exposed", [0]))

    def test_exposure_evidence_must_stay_preserved(self) -> None:
        self._reject(lambda d: d["freeze"]["exposure"]["evidence"].__setitem__("preserved", False))

    def test_nothing_may_be_tuned_in_response_to_the_exposed_verdict(self) -> None:
        self._reject(
            lambda d: d["freeze"]["exposure"].__setitem__(
                "tuning_in_response", "latency grid narrowed after seeing UNSTABLE"
            )
        )

    def test_exposure_must_remain_reportable_in_findings(self) -> None:
        self._reject(lambda d: d["freeze"]["exposure"].__setitem__("must_be_reported_in_findings", False))

    def test_exposure_status_cannot_be_downgraded(self) -> None:
        self._reject(lambda d: d.__setitem__("status", "FROZEN_PRE_RESULT"))

    def test_confirmatory_run_cannot_self_authorise(self) -> None:
        self._reject(lambda d: d.__setitem__("confirmatory_status", "AUTHORIZED"))

    def test_confirmation_seed_set_cannot_drift(self) -> None:
        self._reject(lambda d: d["seed_policy"].__setitem__("confirmation_seeds", list(range(100, 120))))

    def test_confirmation_seeds_cannot_overlap_the_exposed_set(self) -> None:
        self._reject(lambda d: d["seed_policy"].__setitem__("confirmation_seeds", list(range(30))))

    def test_confirmation_seeds_must_stay_pre_registered(self) -> None:
        self._reject(
            lambda d: d["seed_policy"].__setitem__(
                "confirmation_seeds_frozen_before_any_further_outcome_access", False
            )
        )

    def test_confirmatory_run_must_use_the_disjoint_set(self) -> None:
        self._reject(lambda d: d["seed_policy"].__setitem__("confirmatory_run_uses", "development_seeds"))

    def test_environment_lock_cannot_be_null(self) -> None:
        self._reject(lambda d: d["reproduction"].__setitem__("environment_lock", None))

    def test_environment_lock_must_enforce_hashes(self) -> None:
        self._reject(lambda d: d["reproduction"]["environment_lock"].__setitem__("hash_enforced", False))

    def test_environment_lock_digest_must_match_the_file(self) -> None:
        """Previously this only checked the string was 64 characters long."""
        self._reject(
            lambda d: d["reproduction"]["environment_lock"].__setitem__("sha256", "0" * 64)
        )

    def test_frozen_horizon_cannot_drift(self) -> None:
        """Reduced scale is what caused the recorded exposure."""
        self._reject(lambda d: d["horizon"].__setitem__("events_per_run_after_warm_up", 5000))

    def test_warm_up_cannot_drift(self) -> None:
        self._reject(lambda d: d["initial_book_state"].__setitem__("warm_up_events_discarded", 1000))

    def test_parent_quantity_cannot_drift(self) -> None:
        self._reject(lambda d: d["participants"]["tracked_agent"].__setitem__("parent_quantity_lots", 50))

    def test_display_size_cannot_drift(self) -> None:
        self._reject(lambda d: d["participants"]["tracked_agent"].__setitem__("display_lots", 1))

    def test_replenishment_semantics_cannot_be_dropped(self) -> None:
        self._reject(
            lambda d: d["participants"]["tracked_agent"].__setitem__("replenishment", "unspecified")
        )

    def test_order_flow_rates_cannot_drift(self) -> None:
        self._reject(lambda d: d["order_flow"].__setitem__("cancel_rate_per_resting_lot_per_sec", 0.5))

    def test_order_size_distribution_cannot_drift(self) -> None:
        self._reject(
            lambda d: d["order_flow"].__setitem__("order_size_distribution_lots", {"1": 1.0})
        )

    def test_bootstrap_seed_cannot_drift(self) -> None:
        self._reject(lambda d: d["seed_policy"].__setitem__("bootstrap_seed", 1))

    def test_declared_implementation_defect_cannot_be_removed(self) -> None:
        self._reject(
            lambda d: d["freeze"].__setitem__(
                "implementation_defects_corrected",
                [x for x in d["freeze"]["implementation_defects_corrected"] if x["id"] != "D1"],
            )
        )

    def test_defect_record_must_say_how_it_was_verified(self) -> None:
        self._reject(lambda d: d["freeze"]["implementation_defects_corrected"][0].__setitem__("verified", ""))

    def test_amendment_log_must_stay_contiguous(self) -> None:
        """Deleting a middle amendment used to pass."""
        self._reject(
            lambda d: d["freeze"].__setitem__(
                "amendments", [a for a in d["freeze"]["amendments"] if a["id"] != "A5"]
            )
        )

    def test_amendment_cannot_be_deleted_and_the_rest_renumbered(self) -> None:
        """Contiguity alone let A17 vanish with A18 onward renumbered into its place."""
        def mutate(d):
            kept = [a for a in d["freeze"]["amendments"] if a["id"] != "A17"]
            for i, a in enumerate(kept, start=1):
                a["id"] = f"A{i}"
            d["freeze"]["amendments"] = kept
        self._reject(mutate)

    def test_past_amendment_text_cannot_be_edited(self) -> None:
        self._reject(lambda d: d["freeze"]["amendments"][3].__setitem__("new_rule", "reworded after the fact"))

    def test_amendments_cannot_be_reordered(self) -> None:
        def mutate(d):
            log = d["freeze"]["amendments"]
            log[1], log[2] = log[2], log[1]
            log[1]["id"], log[2]["id"] = "A2", "A3"
        self._reject(mutate)

    def test_defect_ids_cannot_be_renumbered(self) -> None:
        def mutate(d):
            kept = [x for x in d["freeze"]["implementation_defects_corrected"] if x["id"] != "D3"]
            for i, x in enumerate(kept, start=1):
                x["id"] = f"D{i}"
            d["freeze"]["implementation_defects_corrected"] = kept
        self._reject(mutate)

    def test_defect_entries_cannot_be_reordered(self) -> None:
        """Same ids, different order: only the comparison with the previous tag sees it."""
        def mutate(d):
            log = d["freeze"]["implementation_defects_corrected"]
            log[2], log[3] = log[3], log[2]
            log[2]["id"], log[3]["id"] = "D3", "D4"
        self._reject(mutate)

    def test_unresolvable_previous_tag_fails_closed(self) -> None:
        with self.assertRaises(AssertionError):
            validator._previous_freeze("no-such-freeze-tag")

    def test_superseded_commit_must_be_a_hash(self) -> None:
        self._reject(lambda d: d["freeze"]["amendments"][0].__setitem__("superseded_commit", "yesterday"))

    def test_freeze_tag_must_be_the_current_version(self) -> None:
        self._reject(lambda d: d["authority"].__setitem__("freeze_tag", "microstructure-freeze-v7"))

    def test_superseded_tag_cannot_be_dropped(self) -> None:
        self._reject(lambda d: d["authority"].__setitem__("superseded_tags", []))

    def test_current_tag_cannot_be_listed_as_superseded(self) -> None:
        self._reject(lambda d: d["authority"]["superseded_tags"].append(d["authority"]["freeze_tag"]))

    def test_amended_date_must_match_the_documents(self) -> None:
        self._reject(lambda d: d.__setitem__("amended_date", "2026-09-20"))

    def test_identity_must_cover_the_executed_matrix(self) -> None:
        self._reject(
            lambda d: d["controls"]["identity_run"].__setitem__(
                "verification", "sha256 equality on sentinel seeds"
            )
        )

    def test_environment_lock_must_predate_the_confirmatory_run(self) -> None:
        self._reject(
            lambda d: d["reproduction"]["environment_lock"].__setitem__(
                "frozen_before_confirmatory_run", False
            )
        )

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



    def _staged(self, tmp: str) -> Path:
        """The three narrative documents beside each other, as validate() expects."""
        for name in ("PROTOCOL.md", "brief.md", "FINDINGS.md"):
            (Path(tmp) / name).write_text(
                (PROTOCOL.parent / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        return Path(tmp) / "PROTOCOL.md"

    def test_the_invalidating_count_must_match_the_severity_fields(self) -> None:
        """The prose said eleven while the contract marked fourteen.

        The sentence was edited in the commit that added three more and the
        edit silently failed to match, so the number stood wrong in both
        documents because nothing read it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            protocol = self._staged(tmp)
            validator.validate(copy.deepcopy(self.data), protocol)

            brief = Path(tmp) / "brief.md"
            text = brief.read_text(encoding="utf-8")
            self.assertIn("Fourteen of them", text)
            brief.write_text(text.replace("Fourteen of them", "Eleven of them"), encoding="utf-8")
            with self.assertRaises(AssertionError):
                validator.validate(copy.deepcopy(self.data), protocol)
            brief.write_text(text, encoding="utf-8")

            # and the other direction: one more invalidating defect, prose untouched
            mutated = copy.deepcopy(self.data)
            mutated["freeze"]["implementation_defects_corrected"].append(
                {"id": "D55", "found_by": "test", "severity": "invalidating",
                 "defect": "x", "fix": "y", "verified": "z"}
            )
            with self.assertRaises(AssertionError):
                validator.validate(mutated, protocol)


    def test_findings_must_account_for_every_defect(self) -> None:
        """Nothing read the findings document, so two defects went unrecorded in it."""
        with tempfile.TemporaryDirectory() as tmp:
            protocol = self._staged(tmp)
            validator.validate(copy.deepcopy(self.data), protocol)
            findings = Path(tmp) / "FINDINGS.md"
            text = findings.read_text(encoding="utf-8")
            self.assertIn("D13", text)
            findings.write_text(text.replace("D13", "the earlier figure"), encoding="utf-8")
            with self.assertRaises(AssertionError):
                validator.validate(copy.deepcopy(self.data), protocol)

    def test_findings_must_account_for_a_newly_added_defect(self) -> None:
        """Appending a defect without writing it up must fail rather than pass quietly."""
        with tempfile.TemporaryDirectory() as tmp:
            protocol = self._staged(tmp)
            mutated = copy.deepcopy(self.data)
            mutated["freeze"]["implementation_defects_corrected"].append(
                {"id": "D99", "found_by": "test", "severity": "minor",
                 "defect": "x", "fix": "y", "verified": "z"}
            )
            with self.assertRaises(AssertionError):
                validator.validate(mutated, protocol)

    def test_narrative_must_cover_every_amendment(self) -> None:
        """The brief summarised A1-A24 then jumped to A36, and nothing noticed."""
        with tempfile.TemporaryDirectory() as tmp:
            protocol = self._staged(tmp)
            validator.validate(copy.deepcopy(self.data), protocol)
            brief = Path(tmp) / "brief.md"
            text = brief.read_text(encoding="utf-8")
            self.assertIn("**A25-A35**", text)
            brief.write_text(text.replace("**A25-A35**", "**A25-A26**"), encoding="utf-8")
            with self.assertRaises(AssertionError):
                validator.validate(copy.deepcopy(self.data), protocol)

    def test_a_blanket_range_does_not_count_as_a_summary(self) -> None:
        """One line naming the whole span answered for every amendment at once."""
        self.assertFalse(validator._covered_by_a_range("A30", "Amendments A1-A69 were made."))
        self.assertTrue(validator._covered_by_a_range("A30", "- **A25-A35** follow"))
        self.assertFalse(validator._covered_by_a_range("A30", "- **A1-A61** follow"))


    def test_a_range_covers_the_amendments_inside_it(self) -> None:
        """The coverage check reads ranges, not just individual ids."""
        self.assertTrue(validator._covered_by_a_range("A30", "- **A25-A35** follow"))
        self.assertTrue(validator._covered_by_a_range("A25", "- **A25-A35** follow"))
        self.assertTrue(validator._covered_by_a_range("A35", "- **A25-A35** follow"))
        self.assertFalse(validator._covered_by_a_range("A36", "- **A25-A35** follow"))
        self.assertTrue(validator._covered_by_a_range("A7", "A7 stands alone"))

    def test_missing_findings_document_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("PROTOCOL.md", "brief.md"):
                (Path(tmp) / name).write_text(
                    (PROTOCOL.parent / name).read_text(encoding="utf-8"), encoding="utf-8"
                )
            with self.assertRaises(AssertionError):
                validator.validate(copy.deepcopy(self.data), Path(tmp) / "PROTOCOL.md")

    def test_document_amended_date_must_match_the_contract(self) -> None:
        """The one-page protocol and the brief had drifted a version behind the contract."""
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("PROTOCOL.md", "brief.md", "FINDINGS.md"):
                (Path(tmp) / name).write_text((PROTOCOL.parent / name).read_text(encoding="utf-8"), encoding="utf-8")
            validator.validate(copy.deepcopy(self.data), Path(tmp) / "PROTOCOL.md")
            stale = (Path(tmp) / "PROTOCOL.md").read_text(encoding="utf-8")
            self.assertIn(f"amended {self.data['amended_date']}", stale)
            (Path(tmp) / "PROTOCOL.md").write_text(
                stale.replace(f"amended {self.data['amended_date']}", "amended 2026-09-20"), encoding="utf-8"
            )
            with self.assertRaises(AssertionError):
                validator.validate(copy.deepcopy(self.data), Path(tmp) / "PROTOCOL.md")

    def test_authorization_block_cannot_be_removed(self) -> None:
        self._reject(lambda d: d.pop("authorization"))

    def test_receipt_cannot_stop_being_the_only_mutable_input(self) -> None:
        self._reject(
            lambda d: d["authorization"].__setitem__(
                "receipt_is_the_only_post_review_mutable_input", False
            )
        )

    def test_authorisation_predicate_cannot_become_a_prefix_test(self) -> None:
        """A prefix test would accept AUTHORIZED_REVOKED. The kind is pinned, not the prose."""
        self._reject(lambda d: d["authorization"].__setitem__("predicate_kind", "string_prefix"))

    def test_predicate_prose_alone_cannot_satisfy_the_pin(self) -> None:
        def mutate(d):
            d["authorization"]["predicate_kind"] = "string_prefix"
            d["authorization"]["predicate"] = (
                "exactly boolean true is not required; no string prefix check is omitted, any AUTHORIZED* passes"
            )
        self._reject(mutate)

    def test_reviewed_sha_rule_cannot_readmit_ancestors(self) -> None:
        self._reject(
            lambda d: d["authorization"].__setitem__(
                "reviewed_sha_rule",
                "full 40-character SHA, and must be this revision or an ancestor of it. The receipt must also name "
                "the reviewed tag, and the gate refuses unless that tag resolves to exactly the named SHA.",
            )
        )

    def test_verified_before_run_must_describe_the_receipt_gate(self) -> None:
        self._reject(
            lambda d: d["reproduction"]["environment_lock"].__setitem__(
                "verified_before_run",
                "reproduce refuses to start unless confirmatory_status is AUTHORIZED and the lock matches",
            )
        )

    def test_interval_alpha_cannot_drift(self) -> None:
        self._reject(lambda d: d["metrics"]["decision_metric"].__setitem__("interval_alpha", 0.1))

    def test_interval_alpha_cannot_drift_with_its_prose(self) -> None:
        """Moving the number and the sentence together must still be refused."""
        def mutate(d):
            d["metrics"]["decision_metric"]["interval_alpha"] = 0.1
            d["metrics"]["decision_metric"]["interval"] = "BCa bootstrap 90 percent confidence interval"
        self._reject(mutate)

    def test_interval_prose_must_agree_with_interval_alpha(self) -> None:
        self._reject(
            lambda d: d["metrics"]["decision_metric"].__setitem__(
                "interval", "BCa bootstrap 90 percent confidence interval"
            )
        )

    def test_robustness_size_distribution_cannot_drift(self) -> None:
        self._reject(
            lambda d: d["robustness_cell"].__setitem__("order_size_distribution_lots", {"2": 1.0})
        )

    def test_receipt_must_keep_naming_the_reviewed_sha(self) -> None:
        self._reject(
            lambda d: d["authorization"].__setitem__(
                "receipt_must_name", ["approved", "contract_id"]
            )
        )

    def test_unstable_alpha_cannot_drift(self) -> None:
        self._reject(lambda d: d["negative_result_criteria"]["UNSTABLE"].__setitem__("alpha", 0.2))

if __name__ == "__main__":
    unittest.main()
