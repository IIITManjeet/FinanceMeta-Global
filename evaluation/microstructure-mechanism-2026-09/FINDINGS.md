# Findings — market microstructure mechanism sprint

**Status: pre-run.** No confirmatory comparison has been executed and no frozen
cell has been inspected, so there is no result in this document yet. It exists
now because the contract obliges the exposure below to be reported here, and
that obligation should not point at a file that does not exist.

Contract `FINANCEMETA-MICROSTRUCTURE-MECHANISM-2026-v8` (amendments A1-A73, defects D1-D54) · gate issue #51 · PR #57

## Primary result

Not yet produced. The confirmatory run is not authorised.

## Accidental pre-run exposure

Two channels executed the frozen mechanisms on frozen **development** seeds
before authorisation. Neither ran at frozen scale and neither touched the
confirmation seed set, but both are unblinding of the comparison family and are
reported here regardless of what the confirmatory run eventually shows. Two
further channels touched **confirmation** seeds without producing anything
that was written, printed or seen; they are recorded because the record is
written by rule, not by judgement about whether an item is embarrassing.

| Channel | Seeds | Scale | Verdict printed | Found by |
|---|---|---|---|---|
| `--quick` verification path | 0–5 | 1,000 + 5,000 events, 108 runs | **yes** | the reviewer |
| automated test suite | 0, 1, 2, 3, 7, 11 | 200–4,000 events, paired arms; 23 frozen-seed call sites across 2 CI runs (`678cb1a`, `cc7627c`) | no | adversarial self-audit |
| authorisation-bypass test, one commit | 100 | 50 + 100 events, one arm, one run per CI run | no | adversarial self-audit |
| gate stubbed during audit, throwaway clone | unknown, possibly none | frozen scale, one arm at most, roughly twenty seconds | no | self-declared during audit |

The fourth channel is the one that bears describing. An auditor testing whether
the receipt gate could be bypassed replaced it with a no-op in a throwaway
clone and invoked the confirmatory command. The process ran for about twenty
seconds before it was killed. How far it got is not established. The auditor
reported seeing no progress line, but stdout was captured by the test runner,
so that is not evidence either way, and `verify_controls` runs first at frozen
scale on sentinel seeds and takes an unknown share of that time; the number of
confirmation-seed cells executed may well be zero. No estimate is given here,
because none can be regenerated, and a disclosed figure that cannot be
regenerated is the defect already recorded as D13. What is established is that
run records are held in memory until the whole matrix completes, so no
`runs.jsonl`, `decision.json`, `summary.json` or `controls.json` was written;
that no metric value or verdict was printed or observed by anyone; and that the
real repository was untouched. The informational content is nil on any reading:
a single arm at most, no pairing, no comparison, no decision rule, and nothing
retained. It is also the direct reason D26
exists: the test guarding the gate asserted only that it raised, so a gate that
silently returned started the real run. The confirmation seed set is left as
it is, for the reason given under D9; whether this incident warrants a fresh
set is the reviewer's call.

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

Recorded because fourteen of them (D1, D2, D5, D11, D12, D15, D16, D19, D20, D21, D22, D32, D40 and D41) would have invalidated the comparison had it been run. D1 to D14 were
found by adversarial self-audit; D15 to D18 were found by the reviewer in the
pre-run technical review of v6; D19 to D30 were found by three independent
adversarial audits of the v8 draft, after v7 had reported the reviewer's P0-1
and P0-2 closed. They were not closed, and that is stated here plainly rather
than folded into the fix descriptions. D31 was found by the builder while
closing D22.

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

- **D13 — a disclosed figure could not be regenerated.** The residual
  replenishment asymmetry was published as 42 percent from a one-off
  measurement at reduced scale; at the frozen scale it is 24.3 percent. A
  companion mean-displayed-size figure was produced by no committed code at all
  and reversed direction under a plausible alternative definition. Both were
  withdrawn rather than overwritten, and a committed diagnostic now produces
  the number so it can be checked instead of asserted.
- **D14 — the frozen-seed override never reached the guard it claimed to
  bypass.** The CLI flag was dead code: it failed closed, which hid the fact
  that the runtime guard did not consult it. Forwarding it turned the dead flag
  into a real bypass, which is D15.

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

Found by three independent adversarial audits of the v8 draft, after the
reviewer's P0-1 and P0-2 had been reported closed:

- **D19 — the frozen seed set was whatever the caller's contract said it was.**
  `--contract` is an unvalidated path, and both the CLI and the runtime guard
  in `run_once` read the protected seeds from it, so a copy with empty seed
  lists executed development seed 0 and printed the outcome. P0-1 was not
  closed. The protected set is now the union of the passed contract's and the
  canonical in-repo contract's seeds, and the guard refuses everything if the
  canonical contract cannot be read.
- **D20, D21, D22 — the receipt gate proved a commit was reachable, not that the
  executing bytes were that commit.** It never looked at the working tree, so
  uncommitted edits to the decision rule passed; it accepted any ancestor of
  HEAD, so any number of unreviewed commits passed; and it never compared the
  contract in use with the reviewed blob, so a copy with `UNSTABLE.alpha` at
  0.9999 and the same `contract_id` was accepted with a self-written receipt.
  P0-2 was not closed. The gate now requires HEAD to equal the reviewed SHA
  exactly, the tree to be clean apart from the receipt, and the contract at its
  canonical path to be byte-identical to `git show <sha>:<path>`. The contract
  is pinned to LF in `.gitattributes` so a checkout cannot rewrite its bytes.
- **D23 — the tag cross-check accepted anything `rev-parse` resolves.**
  `reviewed_tag: "HEAD"`, a branch name or a short SHA satisfied it vacuously.
  The tag must now equal the contract's `freeze_tag` and resolve through
  `refs/tags/`.
- **D24 — the confidence level of the primary decision was a keyword default.**
  `bca_interval` carried `alpha=0.05` and `decide()` never passed it; the
  contract had only prose. The same class as D18, which had been reported
  closed. `interval_alpha` is now a field, pinned, reconciled with the prose,
  loaded with no default and passed to every bootstrap call.
- **D25 — the amendment log's append-only property lived in git history, not in
  the validator.** Deleting A17 and renumbering passed. The validator now reads
  the contract at the previous freeze tag and requires the current log to
  extend it exactly, failing closed if the tag cannot be resolved; the contract
  workflow checks out full history so it can.
- **D26 — the test guarding the confirmatory entry point asserted only that it
  raised.** A gate that returned would have started the real run, and in the
  audit it did. A structural test now requires the gate to be the first thing
  `main()` does after argument parsing, with nothing able to catch it, and it
  never calls `main()`.
- **D27 — the pro-rata participation floor was a module literal** that the
  contract's field could drift from silently. It is carried on the configuration
  and passed to `allocate()` on every call; the robustness cell's constant size
  distribution, also a literal, is bound the same way.
- **D28 — the authorisation predicate was pinned by substrings of prose.** A
  `predicate_kind` field is pinned instead; the prose is description only.
- **D29 — the contract still described the pre-D16 gate**, saying the run
  refuses unless `confirmatory_status` is AUTHORIZED, which no code reads. The
  text now describes the receipt gate.
- **D30 — `allow_frozen_seed=True` was sufficient**, and the scanner keeping it
  out of tests looked at `src/` only, the D9 shape again. The flag is now
  honoured only for a contract whose receipt has been validated in the same
  process, so it is inert from a test and no scanner exemption exists.
- **D31 — nothing tied the executing code to the reviewed worktree.** A package
  installed elsewhere would have passed a clean tree at the reviewed SHA. The
  gate refuses unless the package file lies inside that worktree.

- **D32 — byte identity covered one file.** The gate compared the contract with
  the reviewed blob and trusted every other tracked file to an empty
  `git status`, but `git status` trusts the index. With
  `update-index --skip-worktree`, an edited decision rule passed; the same
  technique on `reproduce.py` let a hollowed-out gate accept a receipt reading
  `approved: false` with an all-zero SHA and grant the real contract id. The
  claim that the gate proved the executed bytes were the reviewed bytes was
  true of one JSON file. The gate now walks `git ls-tree` and compares the blob
  hash of the bytes on disk for every tracked path, which the index cannot
  influence; `git status` is kept only for untracked additions.
- **D33 — the canonical contract was an unverified anchor.** `frozen_seeds`
  read it from disk, and nothing outside the receipt gate checks it, so editing
  it in place emptied the protected set and the guard admitted development seed
  0. This is D19 moved one hop, from the path a caller supplies to the fixed
  path nothing double-checks. The set is now a union of three, including the
  contract as committed at HEAD. The bypass was demonstrated at the guard
  function; it was not carried through to execution, because that would have
  meant running a frozen seed.
- **D34 — two frozen parameters were bound but not pinned.** Replacing
  `attenuation_ratio_max` and `unstable_sign_test_alpha` with literals left the
  whole suite passing. The binding had been checked from contract to `Config`
  and never from `Config` to use, which is why the class recorded as closed in
  D18 and D24 came back. D18's verification text is corrected to say what it
  actually established.
- **D35 — the frozen-seed grant was keyed on a free-text string.** Any
  configuration sharing the contract id satisfied it, whatever bytes it came
  from. The grant is now keyed on the id together with the sha256 of the
  contract.
- **D36 — the written record drifted where nothing checked it.** The amendment
  summary here skipped A25 to A35 and two defects had no entry, because the
  validator read `PROTOCOL.md` and `brief.md` and never opened this file. It
  now requires this document to account for every defect the contract carries.

- **D37 — a required field was never produced.** The data contract asks for a
  record sha256 for every run beside the intent-stream digest. It was listed
  from the freeze and pinned by nothing, so nothing failed while it went
  undelivered, and a reader had no way to tell an altered run record from an
  original. `to_record` now carries a digest of itself, and the required fields
  are a machine-readable list the validator checks.
- **D38 — two required reported artifacts were produced by nothing.** The
  contract requires a mechanism comparison table and a latency sensitivity plot;
  the run wrote only JSON, so both would have been made by hand and sent as
  figures no committed code generates, which is what D13 was about. The run now
  writes `comparison.md` and `latency_sensitivity.svg`. The plot is SVG built in
  this repository, so no plotting dependency enters the hashed wheel lock.
- **D39 — the decision metric was a literal.** Which metric decides the
  experiment is the most consequential frozen choice the contract makes, and it
  was the last one still written into source. It is read from the contract now.
- **D40 — verifying the source did not prove what the interpreter runs.** A
  cached `.pyc` whose header matches its source is used in preference to that
  source, and `__pycache__` is untracked and ignored, so the gate's own
  `git status` call reported nothing for it and its filter read only untracked
  entries in any case. An audit showed bytecode planted there executing in
  place of source that still hashed correctly, and caches for exactly these
  modules were sitting in the working repository. The gate now requires the
  import path to hold reviewed files and nothing else.
- **D41 — the gate refused every file on a checkout that converts line
  endings.** The walk hashed raw bytes, and the committed blobs are LF, so a
  CRLF working tree differed from every blob while being exactly what git would
  record. It went unnoticed because the tree was checked with `git status`,
  which normalises, rather than with the walk itself. The walk now asks git for
  the object id it would store.
- **D42 — the comparison table differenced a measure the contract forbids
  differencing.** The queue measure is volume ahead in lots under FIFO and a
  size share under pro-rata; the contract says in terms that the two are never
  differenced. The delivered table subtracted one from the other. No test
  caught it because the fixture used only the two metrics where differencing is
  valid. Those metrics are a machine-readable list now, and the table reports
  them side by side with no difference column.
- **D43 — a cache remembered a failure as if it were an answer.** The committed
  canonical seed set was cached on first use including when the read failed, so
  one transient git error disabled that layer for the life of the process. Only
  successful reads are cached now.
- **D44 — a derived configuration inherited the authorisation.** The grant was
  keyed on the contract id and the file digest, both of which
  `dataclasses.replace` copies unchanged, so a configuration with an arbitrary
  scale, horizon or seed set satisfied it. The grant is keyed on the
  configuration itself now.
- **D45 — the required fields and artifacts were pinned in one direction
  only.** Each was compared with a list inside the validator, and nothing
  compared either with what the code produces. That is how the record digest
  went undelivered from the freeze onwards, and the fix for it left the same
  direction unchecked.
- **D46 — the check against narrative drift could itself be satisfied
  vacuously.** Any range counted as covering the amendments inside it, so a
  single line naming the whole span answered for every amendment at once. A
  range wide enough to swallow the log no longer counts.
- **D47 — a test did not test half of what it named.** It corrupted two files
  by replacing a substring present in one and absent from the other, so the
  second edit was a silent no-op, and it passed on Windows only because writing
  the text back rewrote the line endings. The `--assume-unchanged` bypass had
  no coverage at all. It appends bytes now and asserts the edit landed.
- **D48 — a binding was pinned by reading the source text.** Splitting the
  literal in two and adding a dead reference to the contract field passed it. A
  behavioural test varies the metric and watches the statistic follow.

- **D49 — the package only had to be somewhere inside the worktree.** A second
  copy under an ignored directory satisfied the check, and the scan for
  unreviewed importable files covered the source root alone, so `build/`,
  `egg-info/` and the tests' caches were unexamined by it and by git at once.
  The editable install's `.pth` file, which holds the path actually imported,
  lives outside the repository and is reviewed by nothing. The executing
  package must now be the reviewed copy at its canonical path.
- **D50 — the artifacts check searched the source for a filename.** Deleting
  the write and leaving the name in a comment passed it. The artifacts are
  written by a function the test calls, and the test reads the directory
  afterwards. D45 closed this direction for the run record and left it open
  here, while saying otherwise.
- **D51 — the count of invalidating defects was wrong in both documents.** The
  contract's severity fields marked fourteen; the prose said eleven. The
  sentence was edited in the commit that added three more, and the edit
  silently failed to match. The validator cross-foots the two now.
- **D52 — the latency plot would plot a forbidden difference.** The table was
  taught that the queue measure is never differenced across mechanisms and its
  neighbour in the same module was not. It refuses now.
- **D53 — a cache that never cached anything.** The store was unreachable
  because the success path returned from inside the `try`, so nothing was kept
  in either direction, and the test written for it passed because the cache was
  always empty. The cache is gone; every call reads fresh.
- **D54 — negative zero printed as `-0`.** The guard against collapsing a small
  number to zero tested inequality with `0.0`, which is false for `-0.0`, so an
  exact zero read as a small negative.

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
- The receipt gate depends on git: it refuses in a clone without the freeze tag,
  with any untracked or modified file other than the receipt, and with any file
  on the import path that the reviewed tree does not contain, which includes a
  compiled cache. Each refusal names its cause.
  This is deliberate; the alternative is a gate that can be talked past.
- The gate cannot verify the bytecode that was already loaded in order to run
  it. It refuses when a cache is present, so an operator following the
  documented procedure runs from source, and the reproduction command disables
  bytecode caching; but a cache planted before the process starts could have
  supplied the gate itself. No in-process check can close that, and it is
  stated rather than implied.
- The receipt's reviewer field is free text. There is no signature and no
  identity check: the gate records who the receipt claims the reviewer was and
  proves nothing about it. Receipt provenance is a paperwork control.
- The append-only guarantee is only as strong as the `microstructure-freeze-v7`
  tag is immutable upstream. Force-moving it makes the comparison pass
  vacuously, because the previous document becomes the current one. Nothing in
  this repository can prove an upstream tag has not been moved, so that
  guarantee rests on repository governance as well as on code.

## Continue / stop decision

Not yet taken. Pending independent pre-run review and run authorisation.

## Claim boundary

Synthetic simulation only. Nothing here supports a claim of real-market alpha,
live execution performance, realized returns, universal market-quality
superiority, investor benefit or exchange deployability, and no claim is made
that either mechanism is a superior market design.
