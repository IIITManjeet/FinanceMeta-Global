# mechsim: mechanism allocation under frozen order flow

**Author:** Manjeet Pathak · **License:** MIT · **Status:** M1 / E1. Executable, contract v8, `PARTIALLY_UNBLINDED_DEVELOPMENT_EXPOSED`; confirmatory run not authorised

A deterministic discrete-event limit-order-book simulator built for one bounded
question: under an identical synthetic order-flow realization and latency model,
how do **price-time priority (FIFO)** and **pro-rata** allocation differ in
execution quality and queue outcomes for a tracked passive parent order?

Prepared against the public evidence gate in
[`build-the-future-11/FinanceMeta-Global` issue #51](https://github.com/build-the-future-11/FinanceMeta-Global/issues/51)
(parent #47). The frozen protocol lives in
[`evaluation/microstructure-mechanism-2026-09/`](../evaluation/microstructure-mechanism-2026-09/).

## What this is not

Synthetic simulation only. It establishes **no** real-market alpha, live
execution performance, realized return, universal market-quality superiority,
investor benefit, or exchange deployability. It makes **no** claim that either
mechanism is a superior market design. The full claim boundary is frozen in
`experiment_contract.json` and enforced in CI.

## Design

Three constraints shape the design:

1. **Mechanism-agnostic core.** `book.py` handles price levels, order lifecycle
   and market-order sweeping identically for both arms. Only
   `mechanisms.allocate` differs. It is a pure function of
   `(resting, demand)` that never reads simulator state, clock or randomness.

2. **State-independent intent stream.** `flow.py` draws every intent *before* a
   book exists, from `(parameters, seed)` alone. Each limit carries an immutable
   `intent_id`; each cancel carries a `target_intent_id` fixed at generation via
   a per-order lifetime `Exp(0.14 x size)`. Nothing is ever chosen against a live
   resting list, which would pick a different order in each arm once allocation
   diverges. So the identity control is a hash comparison rather than a promise,
   and any divergence is down to the allocation rule.

3. **Controls fail closed.** `reproduce.py` verifies the analytic sanity case
   and the frozen under-allocation examples, the identity control, deterministic
   replay, and the zero-latency cell *before* running any comparison. A broken
   control kills the causal claim, so numbers produced past that point would be
   worse than none.

## Install

```bash
python -m pip install --require-hashes -r microstructure-sim/requirements.lock.txt
python -m pip install -e microstructure-sim --no-deps --no-build-isolation
```

Both lines matter. The lock pins exact versions with hashes on CPython 3.12,
including the build backend, and `--no-build-isolation` stops pip fetching that
backend fresh and unhashed outside the lock. `reproduce` refuses to run under any
other interpreter and verifies this lock against the digest recorded in the
contract before a single cell executes. On Windows set `PYTHONUTF8=1`.

## Reproduce

One command, from the repository root:

```bash
python -m mechsim.reproduce --contract evaluation/microstructure-mechanism-2026-09/experiment_contract.json
```

It verifies the four controls, executes all 540 frozen runs (2 mechanisms × 8
latency points × 30 seeds, plus the 60-run robustness cell), and writes to
`results/`:

| File | Contents |
|---|---|
| `runs.jsonl` | One machine-readable record per run, with stream digest and degeneracy flags |
| `summary.json` | Per-cell distributional summaries (median, IQR, p5, p95), never means alone |
| `decision.json` | The frozen decision rule applied: point estimate, BCa 95% CI, verdict |
| `controls.json` | Control results and identity digests |
| `environment.txt` | Source commit, contract sha256, Python version, full `pip freeze` |

Roughly 13 minutes single-threaded at frozen scale.

It does not start without authorisation. A receipt at
`evaluation/microstructure-mechanism-2026-09/authorization.json` must approve
this contract id at the freeze tag and the exact HEAD SHA, the working tree
must be clean apart from that receipt, the contract on disk must be
byte-identical to the reviewed blob, and the package executing must live inside
that worktree. A commit after review needs a fresh review. Only a validated
receipt lets `run_once` execute a frozen seed; the opt-in flag alone is inert.

`--smoke` is the only safe pre-authorisation check. It is outcome-blind by
construction: sentinel seeds outside every frozen set, shape and invariant
checks only, the decision rule never called, no run record and no verdict. The
pre-run controls also take sentinel seeds and never read the frozen sets, and a
meta-test fails the build if any test module executes a frozen seed. The former
`--quick` mode executed the frozen mechanisms on frozen seeds and printed a
verdict; it is gone, and the exposure is recorded in the contract and in
`FINDINGS.md`.

Other entry points:

```bash
python -m mechsim.cli verify        # the four frozen controls, sentinel seeds only
python -m mechsim.cli run --mechanism PRO_RATA --seed 900000001 --latency-ms 5
```

## Tests

```bash
python -m pytest microstructure-sim -q
```

162 tests covering allocation semantics for both mechanisms, the frozen analytic
and under-allocation cases, book mechanics, the intent-stream schema, the
identity and determinism controls, Perold shortfall over the whole parent order,
the paired bootstrap, sign test and verdict precedence, and guards that keep the
smoke path outcome-blind and the receipt gate honest, the latter against a
throwaway git repository built per test. `run_once` refuses a development or
confirmation seed at runtime unless an authorisation receipt has been validated
in the same process, which only the confirmatory run does, so the CLI example
above uses a sentinel seed. The protected seed set is read from the canonical
contract as well as from any contract passed, so a doctored copy cannot unlock it.

## Declared limitations

These bound any result. All of them were written down before the run, not found
afterwards:

- **No strategic size inflation.** Zero-intelligence agents do not adjust order
  size, so the simulator cannot reproduce the size inflation that is pro-rata's
  main real-world behavioural consequence.
- **Zero fees.** Maker-taker pricing interacts strongly with pro-rata and would
  confound the comparison, so it is frozen out.
- **Background latency is declarative.** Zero-intelligence agents do not react,
  so only the tracked agent's latency has a dynamic effect. The zero-latency
  control is therefore the tracked-agent-0 ms cell of the main grid, not a
  separate cell, and **no latency parity is claimed at any cell**. This bounds
  what the latency sweep can demonstrate.
- **Replenishment churn is asymmetric.** The tracked order is topped up to full
  display after a partial fill, but pro-rata triggers that top-up about 24% more
  often than FIFO at the frozen scale, and each episode resets queue position. Disclosed rather than
  engineered away, because it is plausibly inherent to the mechanisms.
- **The robustness cell moves depth as well as size.** Constant 1-lot background
  orders also change aggregate depth and per-order lifetime, so
  `ASSUMPTION_DRIVEN` indicates sensitivity to that joint change.

Contract details that were under-specified at freeze time are resolved in the
frozen contract itself and in the append-only amendment log inside
[`experiment_contract.json`](../evaluation/microstructure-mechanism-2026-09/experiment_contract.json).
