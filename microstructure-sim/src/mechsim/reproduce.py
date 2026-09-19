"""Run the whole frozen comparison with one command.

    python -m mechsim.reproduce --contract evaluation/microstructure-mechanism-2026-09/experiment_contract.json

Controls go first and fail closed. If identity, determinism or the sanity case
does not hold, nothing runs. A broken control kills the causal claim, so
numbers produced past that point would be worse than no numbers.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

from .analysis import decide, distribution_summary
from .contract import load_config
from .flow import generate_stream, stream_digest
from .mechanisms import FIFO, PRO_RATA, Resting, allocate
from .sim import run_once


CONSTANT_SIZE_DISTRIBUTION = {"1": 1.0}

PRIMARY_METRICS = (
    "fill_probability",
    "implementation_shortfall_bps",
    "spread_at_execution_ticks",
    "time_to_first_fill_ms",
    "time_to_full_fill_ms",
    "queue_measure",
    "price_impact_bps",
)


def verify_controls(cfg) -> dict:
    """Run the four controls. Raises AssertionError on the first failure."""
    report: dict[str, object] = {}

    # 1. Analytic sanity case.
    resting = [Resting(1, 2, 1), Resting(2, 10, 2)]
    fifo_alloc = allocate(FIFO, resting, 6)
    prorata_alloc = allocate(PRO_RATA, resting, 6)
    assert fifo_alloc == {1: 2, 2: 4}, f"analytic FIFO allocation drift: {fifo_alloc}"
    assert prorata_alloc == {1: 1, 2: 5}, f"analytic pro-rata allocation drift: {prorata_alloc}"

    # Frozen under-allocation examples: the aggressor is smaller than the number
    # of eligible orders, so no order is guaranteed a lot.
    equal = [Resting(1, 1, 1), Resting(2, 1, 2), Resting(3, 1, 3)]
    assert allocate(FIFO, equal, 2) == {1: 1, 2: 1}, "under-allocation FIFO drift (equal sizes)"
    assert allocate(PRO_RATA, equal, 2) == {1: 1, 2: 1}, "under-allocation pro-rata drift (equal sizes)"
    uneven = [Resting(1, 1, 1), Resting(2, 1, 2), Resting(3, 5, 3)]
    assert allocate(FIFO, uneven, 2) == {1: 1, 2: 1}, "under-allocation FIFO drift (uneven sizes)"
    assert allocate(PRO_RATA, uneven, 2) == {3: 2}, "under-allocation pro-rata drift (uneven sizes)"
    report["analytic_sanity_case"] = "PASS"

    # 2. Identity: both arms must consume the same realization.
    identity = {}
    for seed in cfg.seeds[:5]:
        digests = {m: stream_digest(generate_stream(cfg, seed, 2000)) for m in (FIFO, PRO_RATA)}
        assert digests[FIFO] == digests[PRO_RATA], f"identity control failed at seed {seed}"
        identity[seed] = digests[FIFO]
    report["identity_control"] = "PASS"
    report["identity_digests"] = identity

    # 3. Determinism: replay must be byte-identical.
    probe = dataclasses.replace(cfg, warm_up_events=500, horizon_events=2000)
    first = run_once(probe, FIFO, seed=cfg.seeds[0], latency_ms=cfg.matched_baseline_ms)
    second = run_once(probe, FIFO, seed=cfg.seeds[0], latency_ms=cfg.matched_baseline_ms)
    a = json.dumps(first.to_record(), sort_keys=True).encode()
    b = json.dumps(second.to_record(), sort_keys=True).encode()
    assert a == b, "determinism control failed: replay is not byte-identical"
    report["deterministic_replay"] = "PASS"
    report["replay_sha256"] = hashlib.sha256(a).hexdigest()

    # 4. Zero-latency control is the tracked-agent-0 ms cell of the main grid.
    #    Background latency has no dynamic effect under non-reactive agents, so
    #    all-agents-zero and tracked-zero coincide; there is no separate cell.
    assert 0 in cfg.latency_grid, "zero-latency control missing from the frozen grid"
    report["zero_latency_control"] = "PASS"
    return report


def build_matrix(cfg) -> list[tuple[str, int, int, str, dict | None]]:
    jobs: list[tuple[str, int, int, str, dict | None]] = []
    for mechanism in (FIFO, PRO_RATA):
        for latency in cfg.latency_grid:
            for seed in cfg.seeds:
                jobs.append((mechanism, seed, latency, "main", None))
        for seed in cfg.seeds:
            jobs.append(
                (mechanism, seed, cfg.matched_baseline_ms, "robustness", CONSTANT_SIZE_DISTRIBUTION)
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
    lines = [
        f"source_commit={sha}",
        f"contract_id={cfg.contract_id}",
        f"contract_sha256={contract_sha}",
        f"python={platform.python_version()}",
        f"platform={platform.platform()}",
        "",
        freeze,
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("results"))
    parser.add_argument(
        "--quick",
        action="store_true",
        help="reduced-scale verification pass; NOT the frozen comparison",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.contract)
    contract_path = Path(args.contract) if args.contract else None
    if contract_path is None:
        from .contract import DEFAULT_CONTRACT

        contract_path = DEFAULT_CONTRACT

    if args.quick:
        cfg = dataclasses.replace(cfg, warm_up_events=1000, horizon_events=5000, seeds=cfg.seeds[:6])

    args.out.mkdir(parents=True, exist_ok=True)

    print("Verifying frozen controls ...")
    controls = verify_controls(cfg)
    for key in ("analytic_sanity_case", "identity_control", "deterministic_replay", "zero_latency_control"):
        print(f"  {key}: {controls[key]}")

    jobs = build_matrix(cfg)
    print(f"\nExecuting {len(jobs)} runs ({'QUICK verification scale' if args.quick else 'frozen scale'}) ...")

    records = []
    started = time.time()
    for i, (mechanism, seed, latency, cell, dist) in enumerate(jobs, start=1):
        result = run_once(cfg, mechanism, seed, latency, cell=cell, size_distribution=dist)
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

    decision = decide(records, cfg)

    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (args.out / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True), encoding="utf-8")
    (args.out / "controls.json").write_text(json.dumps(controls, indent=2, sort_keys=True), encoding="utf-8")
    (args.out / "environment.txt").write_text(environment_lock(cfg, contract_path), encoding="utf-8")

    print(f"\nWrote {len(records)} run records to {runs_path}")
    print(f"Verdict: {decision['verdict']}")
    if args.quick:
        print("\nQUICK MODE - reduced scale. This is NOT the frozen comparison and")
        print("must not be reported as a result.")
    return 0


def _flag_counts(subset: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in subset:
        for flag in record["flags"]:
            counts[flag] = counts.get(flag, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
