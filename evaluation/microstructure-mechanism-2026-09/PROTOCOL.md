# Market microstructure sprint: frozen protocol (one page)

**Contract** `FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v1` · **Status** `FROZEN_PRE_RESULT` · **Frozen** 2026-09-19
**Builder** Manjeet Pathak · **Gate** issue #51 (parent #47) · Machine-readable detail: `experiment_contract.json`

## Question
Under an identical prespecified synthetic order-flow realization and latency model, how do **price-time priority** and **pro-rata** allocation differ in execution quality and queue outcomes for a tracked passive parent order? No direction is predicted.

## Mechanisms (exactly two, frozen before any comparison)
- **A. FIFO:** fills in `(price, arrival_sequence)` order; strict arrival tie-break, no randomization.
- **B. PRO_RATA:** proportional to resting size at best price; largest-remainder rounding; ties by `arrival_sequence`; minimum allocation 1 lot; residual swept FIFO.
- Held constant: book format, order-flow realization, latency model, participant assumptions, fees, initial book.

## Order flow
Zero-intelligence Poisson, **state-independent by design**: the exogenous stream cannot react to fills, which is what makes the identity control checkable rather than a promise. Limit orders 1.2/level/s across 5 levels; market orders 0.9/side/s; cancels 0.14 per resting lot/s; sizes `{1: .5, 2: .25, 5: .15, 10: .1}` lots; tick 1; initial mid 1000. Warm-up 10,000 events discarded; horizon 100,000 events.

## Participants
Background: non-adaptive zero-intelligence agents, no strategic response to mechanism. Tracked agent: passive buy parent of 500 lots, 10 displayed, cancel-replace on best-bid move, benchmarked to arrival mid.

## Latency
Constant per-agent one-way, no jitter. Tracked agent swept over **{0, 1, 2, 5, 10, 25, 50, 100} ms**; background fixed 5 ms; matched baseline **5 ms**.

## Seeds
Seeds 0-29 (30). Failed seeds may **not** be discarded. Bootstrap seed 424242.

## Metrics (all five primary, reported every run)
fill probability · implementation shortfall (bps) · spread at execution · queue position **and** wait time · price impact.
Queue is mechanism-specific by necessity: `volume_ahead_at_best` under FIFO, `size_share_at_best` under pro-rata, which is the quantity that actually determines allocation. Wait time (`time_to_first_fill`, `time_to_full_fill`) is mechanism-neutral and reported for both.

**Decision rule keyed to one metric** to prevent post-hoc selection: implementation shortfall (bps), lower-is-better, mean difference `PRO_RATA − FIFO` at 5 ms, BCa bootstrap 95% CI, 10,000 resamples.
Distributional summaries (median, IQR, p5, p95) are required; means-only reporting is prohibited.

## Controls
1. **Identity run.** sha256 of the serialized exogenous event stream must match across mechanisms per seed.
2. **Zero-latency control.** All agents at 0 ms (in grid).
3. **Analytic sanity case.** 6-lot aggressor meets resting X=2 (seq 1), Y=10 (seq 2): FIFO → X 2, Y 4; pro-rata → X 1, Y 5.
4. **Deterministic replay.** Byte-identical per-run record from `(seed, config)`.

## Prespecified robustness cell (exactly one)
`constant_order_size`: size distribution replaced by constant 1 lot at 5 ms, removing the heterogeneity pro-rata depends on.

## Run matrix
Main 2 × 8 × 30 = **480**; robustness 2 × 1 × 30 = **60**; **total 540**. No run may be excluded after the fact; empty-book, timeout and degenerate runs are retained and reported, with at least three retained failure/edge cases described.

## Negative-result criteria (frozen; a negative result is a valid completion)
- **NULL.** The 95% CI for the decision-metric difference contains zero at the matched baseline.
- **UNSTABLE.** The sign of the difference flips across the frozen seeds.
- **LATENCY_DRIVEN.** Any difference at baseline vanishes in the zero-latency control.
- **ASSUMPTION_DRIVEN.** Any difference collapses in the `constant_order_size` cell.

No parameter changes because a mechanism looks better or worse. **No third mechanism is added after a null result.** Any unavoidable correction is appended to the amendment log with timestamp, old rule, new rule, reason, both SHAs, and whether outcomes had been seen, never by silent rewrite.

## Declared limitations
Zero-intelligence agents do not inflate order size, so the simulator **cannot** reproduce strategic size inflation, which is pro-rata's main real-world behavioural consequence. Fees are zero by design because maker-taker interacts strongly with pro-rata and would confound the comparison.

## Claim boundary
Synthetic simulation only. Conclusions hold solely for these two mechanisms under this frozen flow, participant set, latency model and fee schedule. This is **not** evidence of real-market alpha, live execution performance, realized returns, universal market-quality superiority, investor benefit, or exchange deployability. No claim is made that either mechanism is a superior market design, and no prior auction or mechanism-design work by the builder is referenced or relied upon.

## Reproduce
```
python -m mechsim.reproduce --contract evaluation/microstructure-mechanism-2026-09/experiment_contract.json
```
