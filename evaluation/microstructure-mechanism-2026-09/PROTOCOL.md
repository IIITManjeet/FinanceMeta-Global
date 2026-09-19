# Market microstructure sprint: frozen protocol (one page)

**Contract** `FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v2` (supersedes v1) · **Status** `FROZEN_PRE_RESULT` · **Frozen** 2026-09-19, amended 2026-09-19
**Builder** Manjeet Pathak · **Gate** issue #51 (parent #47) · **PR** #57 · **Tag** `microstructure-freeze-v2`
Machine-readable detail and the append-only amendment log: `experiment_contract.json`

## Question
Under an identical prespecified synthetic order-flow realization and latency model, how do **price-time priority** and **pro-rata** allocation differ in execution quality and queue outcomes for a tracked passive parent order? No direction is predicted.

## Mechanisms (exactly two, frozen before any comparison)
- **A. FIFO:** fills in `(price, arrival_sequence)` order; strict arrival tie-break, no randomization.
- **B. PRO_RATA:** proportional to resting size at best price; largest-remainder rounding; ties by `arrival_sequence`; minimum allocation 1 lot as a **participation floor, not a guarantee**; residual swept FIFO. When the aggressor quantity is below the number of eligible orders, no order is guaranteed a lot; two worked examples are frozen in the contract.
- Held constant: book format, order-flow realization, latency model, participant assumptions, fees, initial book.

## Order flow and event schema
Zero-intelligence Poisson, **state-independent by design**: the whole intent stream is drawn before any book exists. Every LIMIT intent carries an immutable `intent_id`. Every CANCEL intent carries a `target_intent_id` fixed at generation, derived as `cancel_at = t + Exponential(0.14 x size)`; a cancel landing on an order that is filled, already cancelled or never placed is a **counted no-op**. Limit prices are **book-relative** offsets (1-5 ticks from the opposite best) resolved on arrival, so absolute prices may differ across arms while the intent is identical. Limit orders 1.2/level/s across 5 levels; market orders 0.9/side/s; sizes `{1: .5, 2: .25, 5: .15, 10: .1}` lots; tick 1. Initial ladder: bids 999-995, asks 1001-1005, 20 lots each, best bid 999 / best ask 1001, spread 2 ticks. Warm-up 10,000 events discarded; horizon 100,000 events, run in full regardless of fill state.

## Participants
Background: non-adaptive zero-intelligence agents, no strategic response to mechanism. Tracked agent: passive buy parent of 500 lots, 10 displayed, cancel-replace on best-bid move, benchmarked to arrival mid.

## Latency
Constant per-agent one-way, no jitter. Tracked agent swept over **{0, 1, 2, 5, 10, 25, 50, 100} ms**; background 5 ms; matched baseline **5 ms**, meaning the tracked agent holds neither advantage nor disadvantage. Background latency has **no dynamic effect** under non-reactive agents: a uniform shift of the background stream is invisible to every outcome.

## Seeds
Seeds 0-29 (30). Failed seeds may **not** be discarded. Bootstrap seed 424242.

## Metrics (all five primary, reported every run)
fill probability · implementation shortfall (bps) · spread at execution · queue position **and** wait time · price impact.

Implementation shortfall is **Perold shortfall over the whole parent order**, including an **opportunity cost** mark on the unfilled remainder: `1e4 * (sum(p_i*q_i) + (Q-E)*P_T - Q*P_0) / (Q*P_0)`. It is therefore defined for every retained run, including zero-fill, which enters as pure opportunity cost. `P_0` and `P_T` use the last mid at which both sides were non-empty, initialised to 1000; carried-forward runs are flagged and retained. No run is excluded or imputed.

Queue measures are **descriptive only** (lots under FIFO, a fraction under pro-rata) and are never differenced across mechanisms; wait time is the cross-mechanism queue comparison.

**Decision rule**, keyed to one metric to prevent post-hoc selection: implementation shortfall, lower-is-better, mean of per-seed differences `PRO_RATA - FIFO` at 5 ms, **paired by seed**, BCa bootstrap 95% CI, 10,000 resamples. Independent resampling of the arms is prohibited. Distributional summaries (median, IQR, p5, p95) required; means-only reporting prohibited.

## Controls
1. **Identity run.** sha256 equality of the serialized pre-mechanism intent stream, per seed, per cell.
2. **Zero-latency control.** The tracked-agent-0 ms cell of the main grid. Because background latency has no dynamic effect, "all agents at 0 ms" and "tracked agent at 0 ms" coincide; this is not a distinct cell.
3. **Analytic sanity case.** 6-lot aggressor meets resting X=2 (seq 1), Y=10 (seq 2): FIFO -> X 2, Y 4; pro-rata -> X 1, Y 5.
4. **Deterministic replay.** Byte-identical per-run record from `(seed, config)`.

## Prespecified robustness cell (exactly one)
`constant_order_size`: background sizes replaced by a constant 1 lot at 5 ms. This removes **background** size heterogeneity only. The tracked display order stays at 10 lots, so pro-rata does **not** reduce to price-time priority in this cell.

## Run matrix
Main 2 x 8 x 30 = **480**; robustness 2 x 1 x 30 = **60**; **total 540**. No run may be excluded after the fact; empty-book, timeout and degenerate runs are retained and reported, with at least three retained failure/edge cases described.

## Negative-result criteria (frozen; a negative result is a valid completion)
- **NULL.** The 95% CI of the mean paired difference at the matched baseline contains zero.
- **UNSTABLE.** Evaluated only when NULL does not hold. Exact two-sided binomial sign test on the per-seed difference signs gives p > 0.05, which for 30 non-zero pairs means a minority sign count of at least 10. A single opposite seed does not trigger it.
- **LATENCY_DRIVEN.** NULL does not hold, the paired CI at 0 ms contains zero, **and** |D0| <= 0.5 x |D5|.
- **ASSUMPTION_DRIVEN.** As above with the `constant_order_size` cell in place of the 0 ms cell.

Labels may overlap; all that hold are reported, and the headline verdict is the first in precedence order NULL -> UNSTABLE -> LATENCY_DRIVEN -> ASSUMPTION_DRIVEN -> DIFFERENCE_DETECTED.

No parameter changes because a mechanism looks better or worse. **No third mechanism is added after a null result.** Corrections are appended to the amendment log with timestamp, old rule, new rule, reason, reviewer reference and whether outcomes had been seen, never by silent rewrite.

## Declared limitations
Zero-intelligence agents do not inflate order size, so the simulator **cannot** reproduce strategic size inflation, which is pro-rata's main real-world behavioural consequence. Fees are zero by design because maker-taker interacts strongly with pro-rata and would confound the comparison.

## Claim boundary
Synthetic simulation only. Conclusions hold solely for these two mechanisms under this frozen flow, participant set, latency model and fee schedule. This is **not** evidence of real-market alpha, live execution performance, realized returns, universal market-quality superiority, investor benefit, or exchange deployability. No claim is made that either mechanism is a superior market design, and no prior auction or mechanism-design work by the builder is referenced or relied upon.

## Reproduce
```
python -m mechsim.reproduce --contract evaluation/microstructure-mechanism-2026-09/experiment_contract.json
```
