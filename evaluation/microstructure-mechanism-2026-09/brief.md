# FinTech Studio 01: frozen builder brief

> Frozen **before implementation**. The simulator did not exist when this brief was committed.
> After this freeze, material changes require an explicit amendment entry below rather than silent rewriting.

## Identity

- Project title: Mechanism allocation under frozen order flow (FIFO vs pro-rata)
- Builder(s): **Manjeet Pathak**
- Lane: `research-workflow-tooling`
- Governing gate: issue #51 (parent #47)
- Contract: `FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v8` (supersedes v1 to v7; amendments A1-A73 and implementation defects D1-D54 logged in `experiment_contract.json`)
- Freeze identity: PR #57 head + tag `microstructure-freeze-v8` + CI artifact `microstructure-mechanism-contract-<sha>`
  (rule in `experiment_contract.json` `authority.freeze_identity_rule`; the SHA is not embedded because this file is part of the commit it would name)
- Freeze timestamp UTC: 2026-09-19, amended 2026-09-23
- Status: `PARTIALLY_UNBLINDED_DEVELOPMENT_EXPOSED`; confirmatory run not authorised pending independent pre-run review
- Development seeds 0-29 with 0-5, 7 and 11 exposed; confirmation seed set 100-129 pre-registered and disjoint, and it is what the confirmatory run uses

## 1. User + problem

A microstructure researcher comparing exchange allocation rules has no cheap way to tell whether an observed execution-quality difference between mechanisms is caused by the **allocation rule** or by the confounds that normally travel with it: different order flow, different latency, different participant behaviour. Venue-level empirical comparisons cannot hold those constant.

## 2. Current failure

Public comparisons of price-time priority and pro-rata are drawn from different contracts, venues, and periods, so flow and latency differ alongside the mechanism. Simulation studies frequently regenerate order flow per mechanism arm, which silently breaks the very comparison being made: the arms no longer see the same realization. Neither approach can demonstrate that both mechanisms received an identical order-flow path.

## 3. Smallest artifact

A deterministic discrete-event limit-order-book simulator with a **mechanism-agnostic core** and exactly two pluggable allocation rules, driven by a **state-independent** exogenous event stream so the identity of the flow across arms is checkable by hash rather than taken on trust. Plus a fail-closed validator that makes this frozen protocol mechanically enforced in CI.

## 4. Data contract

- Source(s): **none. Fully synthetic.** No market data, no vendor feed, no personal data.
- Exact version / snapshot identity: generated from frozen parameters plus the confirmation seeds 100-129; the contract JSON *is* the data provenance.
- Required fields per run: mechanism, seed, latency, all five primary metrics, degenerate-run flags, no-op counts, intent-stream sha256, record sha256.
- Event identity: every limit intent carries an immutable `intent_id` and every cancel a fixed `target_intent_id`, both drawn before any book exists, so the arms consume the same intents rather than resolving a draw against their own diverging books.
- Timestamp convention: simulated milliseconds from run start; no wall-clock dependence.
- Privacy/licensing: no personal data; MIT.
- Missing/conflicting-data behavior: an empty book, an unfilled parent, or a timeout is a **retained result**, never a dropped run.
- Fails closed when: the identity hash differs across mechanisms for a seed; a replay is not byte-identical; the contract validator rejects the contract.

## 5. Primary evaluation metric

Issue #51 names **five** primary metrics and all five are reported for every run: fill probability, implementation shortfall (bps), spread at execution, queue position and wait time, price impact.

To satisfy #47's single-primary requirement without contradicting #51, one metric is designated the **decision metric**, and the pass/fail rule keys to it alone:

- Metric: **implementation shortfall (bps)**, Perold shortfall over the **whole** parent order, including an opportunity-cost mark on the unfilled remainder at the frozen horizon. It is defined for every retained run, including zero-fill, so no run is excluded or imputed and every seed pair is complete by construction.
- Direction: `lower-is-better`
- Evaluation cell: reference cell at 5 ms, confirmation seeds 100-129
- Decision rule: mean of per-seed differences `PRO_RATA - FIFO`, **paired by seed**, BCa bootstrap 95% CI, 10,000 resamples, bootstrap seed 424242. Independent resampling of the two arms is prohibited. A CI containing zero is declared **NULL** and is a valid completion.

Executed-only shortfall was rejected: because the mechanisms can differ in fill probability, it would compare different selected subsets of the parent order and flatter whichever mechanism fills less.

## 6. Secondary checks

1. **Identity control.** sha256 equality of the serialized exogenous event stream across both mechanisms, per seed.
2. **Determinism.** Byte-identical per-run record on replay from `(seed, config)`.
3. **Analytic sanity.** The frozen 6-lot allocation case resolves to the exact lot splits fixed in the contract.
4. **Zero-latency control.** The tracked-agent-0 ms cell of the main grid. Background latency has no dynamic effect under non-reactive agents, so all-agents-zero and tracked-zero coincide and no separate cell exists.

## 7. Guardrails

- privacy / sensitive data: none. Fully synthetic, no personal or licensed data.
- credential/security handling: no network access, no credentials, no external calls at any point.
- leakage / lookahead: the tracked agent observes only its own post-latency view; no future event is visible to any agent.
- **participant-assumption honesty:** zero-intelligence agents do not inflate order size, so this simulator **cannot** reproduce strategic size inflation, which is the main real-world behavioural consequence of pro-rata. Declared here, before results, not in the findings afterward.
- **fee confound:** fees are frozen at zero because maker-taker interacts strongly with pro-rata and would confound the mechanism comparison. This bounds the result.
- financial-advice boundary: no advice, no alpha claim, no realized-return claim.
- user-harm / misleading-output boundary: no claim that either mechanism is a superior market design; no cross-reference to unrelated prior auction or mechanism-design work by the builder.

## 8. Failure condition

The prototype is **not worth continuing** if any of the following holds, and each is reported rather than repaired:

- the identity control fails, so the arms cannot be shown to share a flow realization and the causal comparison is void;
- replay is not byte-identical, so no result is reproducible;
- the analytic sanity case does not reproduce the frozen allocation;
- the decision-metric difference is **UNSTABLE**, meaning that where NULL does not hold, an exact two-sided binomial sign test on the per-seed difference signs gives p > 0.05 (for 30 non-zero pairs, a minority sign count of at least 10). UNSTABLE is evaluated only when NULL does not hold, so a NULL result is never also a stop condition.

A **NULL** result is *not* a failure condition. It is a valid completion and will be retained and reported as such.

## Reproduction plan

```text
python -m mechsim.reproduce --contract evaluation/microstructure-mechanism-2026-09/experiment_contract.json
```

## Amendments after freeze

The machine-readable log is `experiment_contract.json` `freeze.amendments` (A1-A73), each entry carrying
timestamp, old rule, new rule, reason, reviewer reference, whether any frozen-scale outcome had been seen,
and the superseded commit. No prior rule is ever deleted. Summary of what moved after the initial freeze:

- **A1-A8** answer the first two pre-result reviews: parent-order decision metric defined for every run,
  mechanism-independent intent schema, paired-by-seed inference, numerical negative-result rules,
  zero-latency control redefined honestly, robustness rationale narrowed, edge semantics and ladder frozen
  as fields, placeholders replaced by an identity rule.
- **A9-A12** answer the accidental-exposure blocker: status moved to
  `PARTIALLY_UNBLINDED_DEVELOPMENT_EXPOSED`, the quick path replaced by an outcome-blind smoke, an exact
  hash-enforced environment lock, and a disjoint confirmation seed set.
- **A13-A19** follow an adversarial self-audit: replenishment semantics specified, pre-run controls moved
  to sentinel seeds with identity asserted over the executed matrix instead, the decision rule made
  fail-closed on incomplete cells, the exposure widened to seeds 7 and 11, the latency parity claim
  withdrawn, the robustness-cell confound declared, and the environment-lock digest corrected to the
  repository blob.

- **A20-A24** follow a second adversarial self-audit: the environment lock closed against sdist
  fallback and an unpinned build backend, a runtime-identity gate before the confirmatory run, seed
  identity enforced rather than seed count, the robustness latency read from the contract instead of
  assumed, and the exposure count made exact for both channels.

- **A25-A35** follow a third and fourth self-audit and the reviewer's pre-run
  technical review of v6: the lock reduced to wheels with no source fallback,
  the install command given with `--no-build-isolation` everywhere it appears,
  the churn figure withdrawn and replaced by a committed diagnostic, the
  single-run override removed, authorisation moved out of the contract into a
  separate receipt, the predicate made an exact boolean, the UNSTABLE
  significance level moved into the contract, and the receipt required to name
  the reviewed tag as well as the SHA.
- **A36-A50** follow three independent adversarial audits of the v8 draft, which showed the reviewer's
  P0-1 and P0-2 had been reported closed in v7 when they were not: the frozen seed set is now defined by
  the canonical contract and not by whichever file is passed, the frozen-seed opt-in is inert until a
  receipt has been validated in the same process, the receipt gate requires the freeze tag itself, HEAD
  exactly, a clean tree and a byte-identical contract, the interval alpha, the participation floor and
  the robustness distribution are read from the contract rather than from source, the amendment log is
  checked against the previous freeze tag, the predicate is pinned by kind, and a fourth exposure
  channel is recorded.
- **A51-A58** follow a second round of three independent adversarial audits,
  which showed the first round's repairs were themselves incomplete: the gate
  now verifies every tracked file against the reviewed tree rather than
  trusting `git status`, the frozen seed set takes in the contract as committed
  at HEAD so an in-place edit cannot empty it, frozen parameters are pinned at
  the point of use rather than at load, the frozen-seed grant is keyed on the
  contract's bytes, and three pieces of prose that described controls the code
  does not implement are corrected.
- **A59** follows a delivery check against this brief's own data contract: the required
  per-run fields are now a machine-readable list in the contract rather than a sentence
  here, because a field required from the freeze had gone undelivered without failing
  anything.
- **A60-A61** follow the same delivery check: the required comparison table and latency
  sensitivity plot are now written by the run rather than assembled by hand afterwards, and
  the decision metric is named by the contract rather than by a literal in the decision rule.
- **A62-A69** follow a third round of independent audits, which found the second round's
  repairs incomplete in turn: the gate now requires the import path to hold reviewed files
  and nothing else, because verifying source does not prove which bytecode runs; the tree
  comparison asks git for the object id it would record, because hashing raw bytes refused
  every file on a checkout that converts line endings; the metrics that may not be
  differenced across mechanisms are named in the contract; the frozen-seed grant is keyed on
  the configuration rather than on two copyable strings; and the contract's required fields
  and artifacts are checked against what the code actually produces.
- **A70-A73** follow a fourth round of independent audits, which found the checks themselves
  weaker than the things they check: the executing package must now be the reviewed copy at its
  canonical path rather than merely somewhere inside the worktree, the declared artifacts are
  written by a function a test can call and inspect, the latency plot refuses a metric that may
  not be differenced, and the validator cross-foots the narrative's count of invalidating
  defects against the severity fields.

Implementation defects found before any confirmatory run are recorded separately in
`freeze.implementation_defects_corrected` (D1-D54). Fourteen of them would have invalidated the comparison
had it been run: the floating-point pro-rata tie-break (D1), the missing display replenishment (D2), and
a decision rule that checked seed count but never seed identity (D5), a pre-run gate that never looked at what was installed (D11), an authorisation status that no code read (D12), a CLI override (D15) and a missing authorisation transition (D16), and, found by audit after those were reported closed, a frozen seed set read from whichever contract was passed (D19) and a receipt gate that proved a commit was reachable without proving the executing bytes were that commit (D20-D22).
