# FinTech Studio 01: frozen builder brief

> Frozen **before implementation**. The simulator did not exist when this brief was committed.
> After this freeze, material changes require an explicit amendment entry below rather than silent rewriting.

## Identity

- Project title: Mechanism allocation under frozen order flow (FIFO vs pro-rata)
- Builder(s): **Manjeet Pathak**
- Lane: `research-workflow-tooling`
- Governing gate: issue #51 (parent #47)
- Contract: `FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v2` (supersedes v1; amendments A1-A8 logged in `experiment_contract.json`)
- Freeze identity: PR #57 head + tag `microstructure-freeze-v2` + CI artifact `microstructure-mechanism-contract-<sha>`
  (rule in `experiment_contract.json` `authority.freeze_identity_rule`; the SHA is not embedded because this file is part of the commit it would name)
- Freeze timestamp UTC: 2026-09-19

## 1. User + problem

A microstructure researcher comparing exchange allocation rules has no cheap way to tell whether an observed execution-quality difference between mechanisms is caused by the **allocation rule** or by the confounds that normally travel with it: different order flow, different latency, different participant behaviour. Venue-level empirical comparisons cannot hold those constant.

## 2. Current failure

Public comparisons of price-time priority and pro-rata are drawn from different contracts, venues, and periods, so flow and latency differ alongside the mechanism. Simulation studies frequently regenerate order flow per mechanism arm, which silently breaks the very comparison being made: the arms no longer see the same realization. Neither approach can demonstrate that both mechanisms received an identical order-flow path.

## 3. Smallest artifact

A deterministic discrete-event limit-order-book simulator with a **mechanism-agnostic core** and exactly two pluggable allocation rules, driven by a **state-independent** exogenous event stream so the identity of the flow across arms is checkable by hash rather than taken on trust. Plus a fail-closed validator that makes this frozen protocol mechanically enforced in CI.

## 4. Data contract

- Source(s): **none. Fully synthetic.** No market data, no vendor feed, no personal data.
- Exact version / snapshot identity: generated from frozen parameters plus seeds 0-29; the contract JSON *is* the data provenance.
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
- Evaluation cell: matched-latency baseline, 5 ms, seeds 0-29
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

_Empty at initial freeze._ Any unavoidable correction is appended here with: timestamp, old rule, new rule, reason, whether any primary outcome had already been seen, and both commit SHAs. No prior rule is ever deleted.
