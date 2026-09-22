"""Run the whole frozen comparison with one command.

    python -m mechsim.reproduce --contract evaluation/microstructure-mechanism-2026-09/experiment_contract.json

Controls go first and fail closed. If identity, determinism or the sanity case
does not hold, nothing runs. A broken control kills the causal claim, so
numbers produced past that point would be worse than no numbers.

There is also `--smoke`, which is the only safe way to exercise the pipeline
before a run is authorized. It is outcome-blind by construction: it uses
sentinel seeds that are in no frozen seed set, never calls the decision rule,
and never writes or prints a verdict. The earlier `--quick` mode did none of
that. It executed the frozen mechanisms on frozen seeds and printed a verdict,
which partially unblinded the comparison. It is gone, and the guard in smoke()
exists so it cannot come back by accident.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

from . import sim
from .analysis import decide, distribution_summary
from .contract import CONTRACT_PATH_IN_REPO, DEFAULT_CONTRACT, frozen_seeds, load_config
from .flow import generate_stream, stream_digest
from .mechanisms import FIFO, PRO_RATA, Resting, allocate
from .reporting import comparison_table, latency_sensitivity_svg
from .sim import run_once


# Deliberately far outside any frozen seed set. A smoke run on these cannot be
# mistaken for, or turned into, a frozen comparison result.
SENTINEL_SEEDS = (900_000_001, 900_000_002)

PRIMARY_METRICS = (
    "fill_probability",
    "implementation_shortfall_bps",
    "spread_at_execution_ticks",
    "time_to_first_fill_ms",
    "time_to_full_fill_ms",
    "queue_measure",
    "price_impact_bps",
)


def verify_controls(cfg, seeds: tuple[int, ...] = SENTINEL_SEEDS) -> dict:
    """Run the four controls. Raises AssertionError on the first failure.

    Runs on sentinel seeds by default and never reads cfg.seeds, so that a
    control pass cannot execute a development or confirmation seed. The
    identity and determinism properties are structural, so sentinel seeds
    demonstrate them exactly as well as frozen ones would.
    """
    for seed in seeds:
        assert seed not in frozen_seeds(cfg), f"controls must not run on frozen seed {seed}"
    report: dict[str, object] = {}

    floor = cfg.min_allocation_lots
    resting = [Resting(1, 2, 1), Resting(2, 10, 2)]
    fifo_alloc = allocate(FIFO, resting, 6, floor)
    prorata_alloc = allocate(PRO_RATA, resting, 6, floor)
    assert fifo_alloc == {1: 2, 2: 4}, f"analytic FIFO allocation drift: {fifo_alloc}"
    assert prorata_alloc == {1: 1, 2: 5}, f"analytic pro-rata allocation drift: {prorata_alloc}"

    # Frozen under-allocation examples: the aggressor is smaller than the number
    # of eligible orders, so no order is guaranteed a lot.
    equal = [Resting(1, 1, 1), Resting(2, 1, 2), Resting(3, 1, 3)]
    assert allocate(FIFO, equal, 2, floor) == {1: 1, 2: 1}, "under-allocation FIFO drift (equal sizes)"
    assert allocate(PRO_RATA, equal, 2, floor) == {1: 1, 2: 1}, "under-allocation pro-rata drift (equal sizes)"
    uneven = [Resting(1, 1, 1), Resting(2, 1, 2), Resting(3, 5, 3)]
    assert allocate(FIFO, uneven, 2, floor) == {1: 1, 2: 1}, "under-allocation FIFO drift (uneven sizes)"
    assert allocate(PRO_RATA, uneven, 2, floor) == {3: 2}, "under-allocation pro-rata drift (uneven sizes)"
    report["analytic_sanity_case"] = "PASS"

    # Identity: both arms must consume the same realization. The generator takes
    # no mechanism argument, so this is structural; the digests record it.
    identity = {}
    for seed in seeds:
        digests = {m: stream_digest(generate_stream(cfg, seed, 2000)) for m in (FIFO, PRO_RATA)}
        assert digests[FIFO] == digests[PRO_RATA], f"identity control failed at seed {seed}"
        identity[seed] = digests[FIFO]
    report["identity_control"] = "PASS"
    report["identity_digests"] = identity

    # Determinism: replay must be byte-identical.
    probe = dataclasses.replace(cfg, warm_up_events=500, horizon_events=2000)
    first = run_once(probe, FIFO, seed=seeds[0], latency_ms=cfg.matched_baseline_ms)
    second = run_once(probe, FIFO, seed=seeds[0], latency_ms=cfg.matched_baseline_ms)
    a = json.dumps(first.to_record(), sort_keys=True).encode()
    b = json.dumps(second.to_record(), sort_keys=True).encode()
    assert a == b, "determinism control failed: replay is not byte-identical"
    report["deterministic_replay"] = "PASS"
    report["replay_sha256"] = hashlib.sha256(a).hexdigest()

    # Zero-latency control is the tracked-agent-0 ms cell of the main grid.
    # Background latency has no dynamic effect under non-reactive agents, so
    # all-agents-zero and tracked-zero coincide; there is no separate cell.
    assert 0 in cfg.latency_grid, "zero-latency control missing from the frozen grid"
    report["zero_latency_control"] = "PASS"
    return report


def smoke(cfg) -> int:
    """Outcome-blind pipeline check. Never touches a frozen seed or the decision rule.

    Exercises shape and invariants on sentinel seeds only. It cannot produce the
    frozen comparison decision: decide() is not called, no run record is written,
    and no verdict is computed or printed.
    """
    frozen = frozen_seeds(cfg)
    for s in SENTINEL_SEEDS:
        assert s not in frozen, f"sentinel seed {s} collides with a frozen seed set"

    print("Verifying frozen controls ...")
    controls = verify_controls(cfg)
    for key in ("analytic_sanity_case", "identity_control", "deterministic_replay", "zero_latency_control"):
        print(f"  {key}: {controls[key]}")

    tiny = dataclasses.replace(cfg, warm_up_events=200, horizon_events=800)
    print(f"\nShape and invariant checks on sentinel seeds {SENTINEL_SEEDS} ...")
    for seed in SENTINEL_SEEDS:
        digests = {}
        for mechanism in (FIFO, PRO_RATA):
            record = run_once(tiny, mechanism, seed, cfg.matched_baseline_ms, cell="sentinel").to_record()
            for key in PRIMARY_METRICS:
                assert key in record, f"missing metric field: {key}"
            assert isinstance(record["implementation_shortfall_bps"], float), "shortfall must be defined"
            assert 0.0 <= record["fill_probability"] <= 1.0, "fill probability out of range"
            assert len(record["stream_sha256"]) == 64, "missing stream digest"
            assert record["cell"] == "sentinel", "sentinel runs must be labelled sentinel"
            digests[mechanism] = record["stream_sha256"]
        assert digests[FIFO] == digests[PRO_RATA], f"identity failed on sentinel seed {seed}"
        print(f"  seed {seed}: fields present, shortfall defined, identity holds")

    print("\nSMOKE PASS - structure only.")
    print("No frozen seed or cell was executed, the decision rule was not called,")
    print("and no run record or verdict was produced.")
    return 0


def _git_bytes(*args: str, cwd: Path) -> bytes | None:
    """Raw git stdout, or None on failure.

    git rev-parse echoes an unresolvable ref back to stdout rather than
    returning nothing, so the exit code is what decides. Every call is anchored
    to a directory rather than the process cwd, so the repository examined is
    the one holding the contract and not whatever the shell happens to be in.
    """
    try:
        done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, check=False)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def _git(*args: str, cwd: Path) -> str:
    out = _git_bytes(*args, cwd=cwd)
    return out.decode("utf-8", "replace").strip() if out is not None else ""


def _disk_blob_ids(worktree: Path, rels: list[str]) -> dict[str, str]:
    """Object id git would record for each path's current content on disk.

    Hashing the raw bytes here instead would report every file as drifted on a
    checkout that stores CRLF, because the committed blobs are LF and git
    normalises on the way in. git hash-object applies the same attributes and
    filters git would apply when staging, so the comparison asks the right
    question on every platform. It reads the file, not the index, so the
    skip-worktree and assume-unchanged tampering this walk exists to catch is
    still caught. .gitattributes decides those filters and is itself a tracked
    file this walk verifies.
    """
    ids: dict[str, str] = {}
    for i in range(0, len(rels), 50):
        batch = rels[i:i + 50]
        out = _git("hash-object", "--", *batch, cwd=worktree)
        lines = out.splitlines()
        if len(lines) != len(batch):
            raise SystemExit("refusing to run: cannot hash the working tree against the reviewed tree.")
        ids.update(zip(batch, lines))
    return ids


def _tree_drift(reviewed: str, worktree: Path) -> tuple[list[str], set[str]]:
    """Tracked paths whose bytes on disk are not the blobs committed at the reviewed SHA.

    Enumerates the committed tree rather than asking git about the working
    copy. git status trusts the index, and update-index --skip-worktree or
    --assume-unchanged makes it report a modified file as clean; an audit hid
    edits to the decision rule and the mechanisms that way, then hollowed out
    this gate itself, and a receipt for a nonexistent contract was accepted.
    Hashing what is on disk against the object ids in the tree is independent
    of the index, and a missing file is caught as well. Every tracked path is
    checked; choosing which files matter is a judgement the gate must not make.
    """
    listing = _git_bytes("ls-tree", "-r", "-z", reviewed, cwd=worktree)
    if listing is None:
        raise SystemExit(f"refusing to run: cannot list the tree committed at {reviewed[:12]}.")
    drift: list[str] = []
    tracked: set[str] = set()
    present: dict[str, str] = {}
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        meta, _, name = entry.partition(b"\t")
        _mode, kind, oid = meta.decode("ascii").split(" ")
        rel = name.decode("utf-8", "surrogateescape")
        tracked.add(rel)
        if kind != "blob":
            drift.append(f"{rel} ({kind}: not verifiable by content)")
        elif not (worktree / rel).is_file():
            drift.append(f"{rel} (missing)")
        else:
            present[rel] = oid
    on_disk = _disk_blob_ids(worktree, sorted(present))
    drift.extend(rel for rel, oid in sorted(present.items()) if on_disk.get(rel) != oid)
    return sorted(drift), tracked


# Directories the interpreter can import from. Anything here that is not a
# reviewed file can change what runs without touching a tracked byte.
# The package's own directory, and every sibling the interpreter could import
# from. Scanning only the source root left build/, tests/__pycache__ and
# egg-info/ unexamined, all of them ignored by git and all of them capable of
# holding a complete second copy of this package.
PACKAGE_PATH_IN_REPO = "microstructure-sim/src/mechsim"
IMPORT_ROOTS = ("microstructure-sim",)


def _foreign_importable(worktree: Path, tracked: set[str]) -> list[str]:
    """Files under the import roots that the reviewed tree does not contain.

    Verifying tracked source proves what the .py files say, not what the
    interpreter runs. Python prefers a cached .pyc whose header matches the
    source, and __pycache__ is untracked and ignored, so git status reports
    nothing for it: the gate's own invocation hides ignored paths, and its
    filter only reads "??" entries. Bytecode planted there executes in place of
    source that still hashes correctly. The same goes for a stray .py or .pth
    that shadows a module. So the import roots must contain reviewed files and
    nothing else.

    This cannot defend against bytecode that was already loaded to run this
    function. That limit is declared in the contract; the check keeps an
    operator following the documented procedure from running a stale or planted
    cache, and the reproduction command disables bytecode caching.
    """
    foreign = []
    for root in IMPORT_ROOTS:
        base = worktree / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(worktree).as_posix()
            if rel not in tracked:
                foreign.append(rel)
    return foreign


def _require_authorisation(contract_path: Path) -> dict:
    """Refuse the confirmatory run until a receipt names exactly this source.

    The receipt is a separate file, not a contract field, and it is the only
    input that may change after the pre-run review. That keeps the reviewed
    contract byte-identical to the executed one: authorising a run cannot
    require editing the frozen document or the validator that pins it.

    Naming a reachable commit is not enough; the gate has to prove the bytes
    about to execute are that commit. An earlier version accepted any number
    of unreviewed commits after the reviewed one, never looked at the working
    tree, and never compared the contract in use with the reviewed blob, so
    an edited decision rule or a doctored contract copy passed with a
    self-written receipt. The version after that compared only the contract
    byte for byte and trusted git status for everything else, which the index
    can be told to lie about. Now the receipt's tag must be the contract's own
    freeze tag and resolve as a tag, its SHA must be HEAD exactly, the contract
    must sit at its canonical path and match the reviewed blob byte for byte,
    every tracked file on disk must hash to the blob recorded in the reviewed
    tree, nothing untracked may exist apart from the receipt, and this package
    must live inside that same worktree.

    The predicate is an exact boolean, not a string prefix. A prefix test would
    accept AUTHORIZED_REVOKED or AUTHORIZED_DO_NOT_RUN.

    What this cannot do is vouch for its own bytes: a copy of this function
    rewritten to skip its checks is not running them. reproduce.py is one of
    the tracked files hashed above, so an edit anywhere else in it is caught,
    but the gate's own logic is established by the review of the reviewed SHA
    and by the operator running that checkout, not by the gate.

    On success the contract id and the sha256 of its bytes are added to
    sim.AUTHORISED_CONTRACTS, which is what lets run_once honour
    allow_frozen_seed=True. Nothing else grants it.
    """
    contract_bytes = contract_path.read_bytes()
    data = json.loads(contract_bytes)
    rule = data["authorization"]
    receipt_path = contract_path.parent / Path(rule["receipt_file"]).name

    if not receipt_path.is_file():
        raise SystemExit(
            f"refusing to run: no authorisation receipt at {receipt_path}. "
            "The confirmatory comparison runs only after independent pre-run review has produced "
            "a receipt naming the reviewed source. Use --smoke for an outcome-blind check."
        )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("approved") is not True:
        raise SystemExit(
            f"refusing to run: authorisation receipt does not approve this run "
            f"(approved={receipt.get('approved')!r})."
        )
    if receipt.get("contract_id") != data["contract_id"]:
        raise SystemExit(
            f"refusing to run: receipt authorises {receipt.get('contract_id')!r}, "
            f"this contract is {data['contract_id']!r}."
        )

    reviewed = str(receipt.get("reviewed_sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", reviewed):
        raise SystemExit("refusing to run: receipt must name the reviewed source as a full 40-character SHA.")

    tag = str(receipt.get("reviewed_tag", ""))
    if not tag:
        raise SystemExit("refusing to run: receipt must name the reviewed tag as well as the SHA.")
    freeze_tag = data["authority"]["freeze_tag"]
    if tag != freeze_tag:
        raise SystemExit(
            f"refusing to run: receipt names tag {tag!r}, but this contract's freeze tag is {freeze_tag!r}."
        )
    repo = contract_path.parent
    # refs/tags/ in full, so that HEAD, a branch name or an abbreviated SHA
    # cannot stand in for the tag and satisfy the cross-check vacuously.
    tagged = _git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}", cwd=repo)
    if not tagged:
        raise SystemExit(f"refusing to run: receipt names tag {tag!r}, which does not resolve here as a tag.")
    if tagged != reviewed:
        raise SystemExit(
            f"refusing to run: receipt is internally inconsistent. Tag {tag} resolves to "
            f"{tagged[:12]}, but the receipt names reviewed source {reviewed[:12]}."
        )

    head = _git("rev-parse", "HEAD", cwd=repo)
    if not head:
        raise SystemExit("refusing to run: cannot resolve the current source revision to check the receipt.")
    if reviewed != head:
        raise SystemExit(
            f"refusing to run: the receipt names reviewed source {reviewed[:12]}, but this revision is "
            f"{head[:12]}. A commit after review is not covered by the review; it needs a fresh one."
        )

    toplevel = _git("rev-parse", "--show-toplevel", cwd=repo)
    if not toplevel:
        raise SystemExit("refusing to run: cannot locate the worktree that holds the contract.")
    worktree = Path(toplevel).resolve()
    try:
        relative = contract_path.resolve().relative_to(worktree).as_posix()
    except ValueError:
        relative = ""
    if relative != CONTRACT_PATH_IN_REPO:
        raise SystemExit(
            f"refusing to run: the contract in use is {contract_path}, not the reviewed document at "
            f"{CONTRACT_PATH_IN_REPO} inside {worktree}."
        )
    # Inside the worktree is not enough. A second copy of the package under an
    # ignored directory, or reached through a .pth or PYTHONPATH that no review
    # covers, satisfies that while running bytes nobody read. The executing
    # package must be the reviewed one, at the path the reviewed tree puts it.
    package = Path(__file__).resolve().parent
    canonical = (worktree / PACKAGE_PATH_IN_REPO).resolve()
    if package != canonical:
        raise SystemExit(
            f"refusing to run: the executing mechsim package is at {package}, not the reviewed copy at "
            f"{canonical}. A second copy reached through PYTHONPATH or a .pth file is not the reviewed "
            "source, whatever the tree says."
        )

    reviewed_blob = _git_bytes("show", f"{reviewed}:{CONTRACT_PATH_IN_REPO}", cwd=repo)
    if reviewed_blob is None:
        raise SystemExit(f"refusing to run: cannot read the contract committed at {reviewed[:12]}.")
    if reviewed_blob != contract_bytes:
        raise SystemExit(
            f"refusing to run: the contract on disk is not byte-identical to the one committed at "
            f"{reviewed[:12]}. The reviewed bytes and the executed bytes must be the same; a checkout that "
            "rewrote line endings fails this too, and .gitattributes pins the contract to LF."
        )

    drift, tracked = _tree_drift(reviewed, worktree)
    if drift:
        raise SystemExit(
            f"refusing to run: {len(drift)} tracked file(s) on disk are not the bytes committed at "
            f"{reviewed[:12]}. Only the receipt may change after review. Differing paths:\n  "
            + "\n  ".join(drift)
        )

    # The index cannot hide an addition the way it hides a modification, so
    # git status is still the right tool for untracked files, and only for them.
    status = _git_bytes("status", "--porcelain", "--untracked-files=all", cwd=repo)
    if status is None:
        raise SystemExit("refusing to run: cannot read the working tree status to check the receipt.")
    receipt_relative = receipt_path.resolve().relative_to(worktree).as_posix()
    untracked = [
        line[3:] for line in status.decode("utf-8", "replace").splitlines()
        if line.startswith("??") and line[3:] != receipt_relative
    ]
    if untracked:
        raise SystemExit(
            f"refusing to run: untracked files exist beside reviewed source {reviewed[:12]}. "
            "Only the receipt may be added after review. Untracked paths:\n  " + "\n  ".join(untracked)
        )

    foreign = _foreign_importable(worktree, tracked)
    if foreign:
        raise SystemExit(
            "refusing to run: the import path holds files the reviewed tree does not contain, so what "
            "the interpreter runs is not what was reviewed. Compiled caches are the usual cause; remove "
            "them and run with python -B. Paths:\n  " + "\n  ".join(foreign)
        )

    digest = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    print(f"Authorisation: receipt {digest[:12]} approves {receipt['contract_id']} at {tag} = {reviewed[:12]} ... OK")
    granted = load_config(contract_path)
    sim.AUTHORISED_CONTRACTS.add(
        (data["contract_id"], hashlib.sha256(contract_bytes).hexdigest(), granted.identity())
    )
    return {"receipt_sha256": digest, "reviewed_sha": reviewed, "reviewed_tag": tag, "head_sha": head,
            "reviewer": receipt.get("reviewer", ""), "granted_utc": receipt.get("timestamp_utc", "")}


def _lock_pins(lock_path: Path) -> dict[str, str]:
    """Package pins declared in the lock file."""
    text = lock_path.read_text(encoding="utf-8")
    return {n.lower().replace("_", "-"): v for n, v in re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", text, re.M)}


def _require_locked_runtime(cfg, contract_path: Path) -> None:
    """Gate the confirmatory run on the frozen runtime and lock, before it runs.

    Three checks, all fail-closed, all before any cell executes:

      1. the interpreter is the frozen major.minor,
      2. the lock file hashes to the digest recorded in the contract,
      3. every distribution actually importable here matches the lock.

    The third one matters most. Hashing the lock file only proves the file has
    not been edited; it says nothing about what pip put in site-packages. An
    audit defeated the earlier version of this gate by installing an unhashed
    numpy over a correctly locked environment, and the gate still reported OK.
    """
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    lock = data["reproduction"]["environment_lock"]

    expected = str(lock["runtime_identity"]).replace("CPython", "").strip()
    actual = platform.python_version()
    if tuple(actual.split(".")[:2]) != tuple(expected.split(".")[:2]):
        raise SystemExit(
            f"refusing to run: frozen runtime identity is {lock['runtime_identity']}, "
            f"this interpreter is CPython {actual}"
        )

    lock_path = Path(__file__).resolve().parents[2] / Path(lock["file"]).name
    if not lock_path.is_file():
        raise SystemExit(f"refusing to run: environment lock missing at {lock_path}")
    digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    if digest != lock["sha256"]:
        raise SystemExit(
            f"refusing to run: environment lock digest mismatch. "
            f"contract {lock['sha256']}, file {digest}"
        )

    drift = []
    for name, pinned in sorted(_lock_pins(lock_path).items()):
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            drift.append(f"{name}: pinned {pinned}, not installed")
            continue
        if installed != pinned:
            drift.append(f"{name}: pinned {pinned}, installed {installed}")
    if drift:
        raise SystemExit(
            "refusing to run: the installed environment does not match the lock.\n  "
            + "\n  ".join(drift)
            + "\nReinstall with: python -m pip install --require-hashes -r "
            + lock["file"]
        )

    print(f"Runtime gate: CPython {actual}, lock {digest[:12]}, {len(_lock_pins(lock_path))} pins verified ... OK")


def build_matrix(cfg) -> list[tuple[str, int, int, str, dict | None]]:
    jobs: list[tuple[str, int, int, str, dict | None]] = []
    seeds = cfg.confirmation_seeds
    for mechanism in (FIFO, PRO_RATA):
        for latency in cfg.latency_grid:
            for seed in seeds:
                jobs.append((mechanism, seed, latency, "main", None))
        for seed in seeds:
            jobs.append(
                (mechanism, seed, cfg.robustness_latency_ms, "robustness", cfg.robustness_size_distribution)
            )
    return jobs


def environment_lock(cfg, contract_path: Path) -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        sha = ""
    try:
        freeze = subprocess.run(
            [sys.executable, "-m", "pip", "freeze", "--all"],
            capture_output=True, text=True, check=False,
        ).stdout
    except OSError:
        freeze = ""
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    lock_path = Path(__file__).resolve().parents[2] / "requirements.lock.txt"
    lock_sha = hashlib.sha256(lock_path.read_bytes()).hexdigest() if lock_path.is_file() else ""
    lines = [
        f"source_commit={sha}",
        f"contract_id={cfg.contract_id}",
        f"contract_sha256={contract_sha}",
        f"requirements_lock_sha256={lock_sha}",
        f"python={platform.python_version()}",
        f"platform={platform.platform()}",
        "",
        freeze,
    ]
    return "\n".join(lines)


def write_artifacts(out: Path, cfg, contract_path: Path, summary: dict, decision: dict,
                    controls: dict, authorisation: dict) -> list[str]:
    """Write every artifact the contract declares, and report what was written.

    These used to be written inline in main(), which meant the only check that
    a declared artifact still gets produced was a search of this file for its
    name. Deleting a write and leaving the name in a comment passed that.
    Calling this is how a test sees what a run actually leaves behind.
    """
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in (
        ("summary.json", json.dumps(summary, indent=2, sort_keys=True)),
        ("decision.json", json.dumps(decision, indent=2, sort_keys=True)),
        ("controls.json", json.dumps(controls, indent=2, sort_keys=True)),
        ("comparison.md", comparison_table(summary, PRIMARY_METRICS, cfg.not_differenced)),
        ("latency_sensitivity.svg",
         latency_sensitivity_svg(summary, cfg.decision_metric_id, not_differenced=cfg.not_differenced)),
        ("environment.txt", environment_lock(cfg, contract_path)),
        ("authorization.json", json.dumps(authorisation, indent=2, sort_keys=True)),
    ):
        (out / name).write_text(text, encoding="utf-8")
        written.append(name)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("results"))
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="outcome-blind pipeline check on sentinel seeds; no frozen cell, no verdict",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.contract)
    contract_path = Path(args.contract) if args.contract else DEFAULT_CONTRACT

    if args.smoke:
        return smoke(cfg)

    authorisation = _require_authorisation(contract_path)
    _require_locked_runtime(cfg, contract_path)

    args.out.mkdir(parents=True, exist_ok=True)

    print("Verifying frozen controls ...")
    controls = verify_controls(cfg)
    for key in ("analytic_sanity_case", "identity_control", "deterministic_replay", "zero_latency_control"):
        print(f"  {key}: {controls[key]}")

    jobs = build_matrix(cfg)
    print(f"\nExecuting {len(jobs)} runs at frozen scale on the confirmation seed set ...")

    records = []
    started = time.time()
    for i, (mechanism, seed, latency, cell, dist) in enumerate(jobs, start=1):
        result = run_once(
            cfg, mechanism, seed, latency, cell=cell, size_distribution=dist, allow_frozen_seed=True
        )
        records.append(result.to_record())
        if i % 25 == 0 or i == len(jobs):
            rate = i / max(time.time() - started, 1e-9)
            print(f"  {i}/{len(jobs)} runs  ({rate:.1f}/s)")

    runs_path = args.out / "runs.jsonl"
    with runs_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    summary: dict[str, dict] = {}
    for cell in ("main", "robustness"):
        for latency in sorted({r["latency_ms"] for r in records if r["cell"] == cell}):
            for mechanism in (FIFO, PRO_RATA):
                subset = [
                    r for r in records
                    if r["cell"] == cell and r["latency_ms"] == latency and r["mechanism"] == mechanism
                ]
                if not subset:
                    continue
                key = f"{cell}|{latency}ms|{mechanism}"
                summary[key] = {
                    metric: distribution_summary([r[metric] for r in subset])
                    for metric in PRIMARY_METRICS
                }
                summary[key]["degenerate"] = {
                    "runs": len(subset),
                    "with_flags": sum(1 for r in subset if r["flags"]),
                    "flag_counts": _flag_counts(subset),
                }

    # Identity across the run matrix that was actually executed. The pre-run
    # control is structural; this is the one that binds the reported records.
    by_cell: dict[tuple[int, int, str], dict[str, str]] = {}
    for r in records:
        by_cell.setdefault((r["seed"], r["latency_ms"], r["cell"]), {})[r["mechanism"]] = r["stream_sha256"]
    for key, arms in sorted(by_cell.items()):
        assert arms.get(FIFO) == arms.get(PRO_RATA), f"identity failed on executed cell {key}"
    controls["identity_across_run_matrix"] = f"PASS ({len(by_cell)} cells)"

    decision = decide(records, cfg)

    write_artifacts(args.out, cfg, contract_path, summary, decision, controls, authorisation)

    print(f"\nWrote {len(records)} run records to {runs_path}")
    print(f"Verdict: {decision['verdict']}")
    return 0


def _flag_counts(subset: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in subset:
        for flag in record["flags"]:
            counts[flag] = counts.get(flag, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
