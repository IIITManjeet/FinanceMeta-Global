# Findings — market microstructure mechanism sprint

**Status: pre-run.** No confirmatory comparison has been executed and no frozen
cell has been inspected, so there is no result in this document yet. It exists
now because the contract obliges the exposure below to be reported here, and
that obligation should not point at a file that does not exist.

Contract `FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v7` (amendments A1-A34, defects D1-D18) · gate issue #51 · PR #57

## Primary result

Not yet produced. The confirmatory run is not authorised.

## Accidental pre-run exposure

Two channels executed the frozen mechanisms on frozen **development** seeds
before authorisation. Neither ran at frozen scale and neither touched the
confirmation seed set, but both are unblinding of the comparison family and are
reported here regardless of what the confirmatory run eventually shows.

| Channel | Seeds | Scale | Verdict printed | Found by |
|---|---|---|---|---|
| `--quick` verification path | 0–5 | 1,000 + 5,000 events, 108 runs | **yes** | the reviewer |
| automated test suite | 0, 1, 2, 3, 7, 11 | 200–4,000 events, paired arms; 23 frozen-seed call sites across 2 CI runs (`678cb1a`, `cc7627c`) | no | adversarial self-audit |

The single exposed outcome is the word `UNSTABLE`, printed once in
[run 35474722869](https://github.com/IIITManjeet/FinanceMeta-Global/actions/runs/35474722869).
No per-cell values, confidence bounds or metric numbers were printed. Nothing
further has been inspected: the run records went to the runner temp directory
and were not retained, and no `runs.jsonl`, `decision.json` or `summary.json`
from any prior execution has been opened.

`UNSTABLE` is, by the frozen precedence, a statement that NULL did not hold on
that subsample — and it is also one of the stop conditions in the frozen brief.
That is the worst single word that could have leaked, and it is recorded plainly
rather than minimised.

One thing does bear on how much that word is worth, and it cuts against the
exposure rather than for it. The verdict was produced by a simulator carrying
D1, D2 and D5 below: a pro-rata tie-break decided by floating-point noise, a
tracked order that was never replenished after a partial fill, and a decision
rule that never checked seed identity. The first two bias the decision metric
directly and in a mechanism-dependent way. Whatever that `UNSTABLE` reflected,
it was not a clean reading of the frozen comparison. This is stated as a fact
about the defective code, not as an argument that the exposure did not matter.

**No parameter was tuned in response.** Mechanisms, metrics, decision rule,
thresholds, labels, latency points, participant assumptions and the 540-cell run
matrix are unchanged. The remedy was a disjoint confirmation seed set, seeds
100–129, pre-registered before any further outcome access, and that is what the
confirmatory run uses.

## Implementation defects corrected before any run

Recorded because seven of them (D1, D2, D5, D11, D12, D15 and D16) would have
invalidated the comparison had it been run. D1 to D14 were found by adversarial
self-audit; D15 to D18 were found by the reviewer in the pre-run technical
review of v6.

- **D1 — pro-rata tie-break decided by floating-point noise.** Exactly equal
  largest-remainder fractions were ordered by float error rather than
  `arrival_sequence`, violating the frozen rule. Measured at 12 violating
  allocations in 5,680 on sentinel runs, with the error correlated with resting
  size — the channel the experiment measures. Fixed with exact integer
  arithmetic and verified against an exact-rational reference over 120,000
  randomised cases, zero mismatches.
- **D2 — the tracked order was never replenished after a partial fill.**
  Displayed size decayed to a mean of 7.72 lots under FIFO and 6.42 under
  pro-rata against a frozen display of 10, so the decay was mechanism-dependent
  and biased the comparison directly. Fixed by cancel-and-replace to full
  display; the residual shortfall is now only the latency window between a fill
  and the replacement landing. **Residual asymmetry, disclosed not corrected:**
  the fix equalises displayed *size* but not replacement *frequency* — pro-rata
  cancel-replaces about 24% more often than FIFO: 214.5 versus 266.6 placements
  per run at the frozen scale, across sentinel seeds 900000001-900000008, with
  pro-rata higher in 8 of 8. Each episode resets queue position and costs a
  latency window, so time-to-fill comparisons inherit it. This is plausibly
  inherent to the mechanisms rather than a defect, so it is declared rather than
  engineered away. Regenerate with
  `mechsim.diagnostics.measure_replenishment_churn`. An earlier revision quoted
  42% and a mean displayed size of 9.15 versus 8.81 lots; both were one-off
  measurements, the first taken at a reduced scale that does not hold at the
  frozen one and the second computed by no committed code. Both are withdrawn.
- **D3 — the decision rule failed open.** A missing or short control cell was
  swallowed, silently suppressing `LATENCY_DRIVEN` or `ASSUMPTION_DRIVEN` and
  upgrading the verdict toward the positive headline; a bootstrap on fewer than
  three pairs returned `NULL` from no data. Both now raise.
- **D4 — the smoke path and the test suite executed frozen seeds** while the
  smoke log asserted the opposite. Controls and tests moved to sentinel seeds,
  with a meta-test that fails the build if any test module executes a frozen
  seed.

Found in a second adversarial audit, after the first four were fixed:

- **D5 — the decision rule checked seed count, not seed identity.** Thirty
  records carrying seeds from no frozen set satisfied the completeness gate and
  returned a clean `LATENCY_DRIVEN` verdict with a point estimate of 4.0. The
  pre-registered confirmation set was therefore not actually binding on the
  statistic. `paired_differences` now takes the expected seed set and raises on
  any mismatch.
- **D6 — duplicate records collapsed silently and non-finite values were not
  checked.** Two contradictory records for the same seed and mechanism resolved
  last-write-wins; a NaN difference reached the bootstrap, where the only thing
  stopping it was an internal numpy percentile bounds check rather than a check
  of ours. Both now raise.
- **D7 — the environment lock did not force hashed installs.** One dependency
  carried only an sdist hash, so `--require-hashes` fell back to building it
  through an unpinned PEP 517 environment, and the package install fetched its
  build backend fresh and unhashed on every invocation. The package README also
  still documented the old unpinned install, contradicting `PROTOCOL.md`, and no
  macOS or arm64 wheel hashes existed, so a reviewer on Apple Silicon could not
  complete a hash-enforced install at all. Every pin now carries a wheel hash,
  the build backend is pinned, installation uses `--no-build-isolation`, and
  wheel coverage spans manylinux x86_64, macOS arm64, macOS x86_64 and win_amd64.
- **D8 — protection against running a frozen seed was a linter, not a guard.**
  The static scan is walked past by an aliased constant, a loop variable, a
  computed value, a helper call, a renamed function or a `conftest.py`, and it
  also mistook `latency_ms=5` for development seed 5. `run_once` now refuses a
  development or confirmation seed at runtime unless the caller explicitly opts
  in, which only the authorised confirmatory run does; the scan is retained as a
  backstop and now inspects only the seed position.

Found in a third adversarial audit, after the second round was fixed:

- **D9 — a test added in the commit that closed the exposure gaps executed
  confirmation seed 100** on every CI run, and the static scanner added
  alongside it was written to exempt exactly that call. The test now proves the
  authorised branch is reachable by intercepting the stream generator, so
  nothing is simulated, and the exemption is gone. The single touch is declared
  in the exposure record: one arm, 150 events, no pairing, no comparison, no
  verdict, and the reduced-scale stream is not a prefix of the frozen one. The
  confirmation seed set is deliberately left unchanged, because altering a
  pre-registered seed set in response would itself be the post-hoc change the
  freeze exists to prevent.
- **D10 — the lock claimed a source-build fallback was impossible while every
  entry carried an sdist hash**, and `PROTOCOL.md` — the document that governs —
  omitted `--no-build-isolation`, so following the frozen protocol literally
  fetched an unpinned build backend from the network. The lock is now
  wheels-only with coverage extended to manylinux aarch64 and musllinux, and one
  identical install command appears in the protocol, the README, CI and the
  contract.
- **D11 — the pre-run gate never looked at what was installed.** It hashed the
  lock file and checked the interpreter string; an unhashed package installed
  over a correctly locked environment passed, and the gate reported OK. It now
  verifies every installed distribution against the lock pins and fails closed
  naming each drift.
- **D12 — no code read `confirmatory_status`.** The contract could record
  NOT_AUTHORIZED while the confirmatory command ran to completion, so the
  requirement to authorise execution only after independent review had nothing
  behind it. The confirmatory path now refuses to start unless the contract
  records an AUTHORIZED status, before any output directory is created.

Found by the reviewer in the pre-run technical review of v6:

- **D15 — the single-run CLI could self-authorise a frozen outcome.** Its
  override passed straight through to the runtime guard without consulting any
  authorisation state, so a confirmation seed could produce an outcome, and be
  inspected individually, before the full comparison was authorised. This was
  introduced by the fix for D14: before that the flag was dead code and failed
  closed, and forwarding it turned a harmless no-op into a real bypass of the
  gate this recovery exists to establish. The override is removed; frozen
  outcomes are reachable only through the authorised confirmatory run.
- **D16 — there was no clean authorisation transition bound to the reviewed
  source.** The validator pinned the status to NOT_AUTHORIZED while the run
  required AUTHORIZED, so authorising meant editing both the contract and the
  validator, advancing the source past the head that had been reviewed.
  Authorisation now lives in a separate receipt naming the reviewed SHA, which
  is the only input permitted to change after review; the contract stays
  byte-identical between review and execution.
- **D17 — the authorisation predicate was a string prefix test** that would have
  accepted `AUTHORIZED_REVOKED`. It is now an exact boolean plus a matching
  contract id and a full reviewed SHA.
- **D18 — the UNSTABLE significance level was a literal in code** rather than a
  field in the contract. It is now an explicit numeric field, pinned and loaded
  with no default.

## Limitations declared before the run

- Zero-intelligence agents do not inflate order size, so the simulator cannot
  reproduce strategic size inflation, pro-rata's main real-world behavioural
  consequence.
- Fees are zero by design; maker-taker interacts strongly with pro-rata and
  would confound the comparison.
- Background latency has no dynamic effect under non-reactive agents, so the
  sweep measures the tracked agent's latency alone and **no latency parity is
  claimed at any cell**.
- The `constant_order_size` robustness cell changes aggregate book depth and
  per-order lifetime alongside size heterogeneity, so `ASSUMPTION_DRIVEN`
  indicates sensitivity to that joint change rather than to size heterogeneity
  alone.
- Development seeds 0–5, 7 and 11 are burned. Any future use of the development
  set is descriptive only.

## Continue / stop decision

Not yet taken. Pending independent pre-run review and run authorisation.

## Claim boundary

Synthetic simulation only. Nothing here supports a claim of real-market alpha,
live execution performance, realized returns, universal market-quality
superiority, investor benefit or exchange deployability, and no claim is made
that either mechanism is a superior market design.
