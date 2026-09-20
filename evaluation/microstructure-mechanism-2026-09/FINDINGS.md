# Findings — market microstructure mechanism sprint

**Status: pre-run.** No confirmatory comparison has been executed and no frozen
cell has been inspected, so there is no result in this document yet. It exists
now because the contract obliges the exposure below to be reported here, and
that obligation should not point at a file that does not exist.

Contract `FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v3` · gate issue #51 · PR #57

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
| automated test suite | 0, 1, 2, 3, 7, 11 | 200–4,000 events, paired arms | no | adversarial self-audit |

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

**No parameter was tuned in response.** Mechanisms, metrics, decision rule,
thresholds, labels, latency points, participant assumptions and the 540-cell run
matrix are unchanged. The remedy was a disjoint confirmation seed set, seeds
100–129, pre-registered before any further outcome access, and that is what the
confirmatory run uses.

## Implementation defects corrected before any run

Found by adversarial self-audit, not by the reviewer. Recorded because two of
them would have invalidated the comparison had it been run.

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
  and the replacement landing.
- **D3 — the decision rule failed open.** A missing or short control cell was
  swallowed, silently suppressing `LATENCY_DRIVEN` or `ASSUMPTION_DRIVEN` and
  upgrading the verdict toward the positive headline; a bootstrap on fewer than
  three pairs returned `NULL` from no data. Both now raise.
- **D4 — the smoke path and the test suite executed frozen seeds** while the
  smoke log asserted the opposite. Controls and tests moved to sentinel seeds,
  with a meta-test that fails the build if any test module executes a frozen
  seed.

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
