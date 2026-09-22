"""Command line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contract import frozen_seeds, load_config
from .mechanisms import FIFO, MECHANISMS
from .reproduce import main as reproduce_main
from .reproduce import verify_controls
from .sim import run_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mechsim")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="execute a single run and print its record")
    p_run.add_argument("--contract", type=Path, default=None)
    p_run.add_argument("--mechanism", choices=MECHANISMS, default=FIFO)
    p_run.add_argument("--seed", type=int, required=True)
    p_run.add_argument("--latency-ms", type=int, default=5)

    p_verify = sub.add_parser("verify", help="run the four frozen controls only")
    p_verify.add_argument("--contract", type=Path, default=None)

    sub.add_parser("reproduce", help="run the full frozen comparison", add_help=False)

    args, rest = parser.parse_known_args(argv)

    if args.command == "reproduce":
        return reproduce_main(rest)

    cfg = load_config(args.contract)

    if args.command == "verify":
        report = verify_controls(cfg)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    # Single-run diagnostics accept non-frozen seeds only, with no override.
    # A flag that unlocked a frozen seed here would let a confirmation outcome be
    # produced, and a confirmation seed inspected individually, before the
    # authorised full comparison. Frozen outcomes are reachable only through
    # mechsim.reproduce, behind the authorisation gate. The frozen set comes
    # from the canonical contract as well as the one passed, because --contract
    # is an arbitrary path and a copy with empty seed lists used to unlock it.
    if args.seed in frozen_seeds(cfg):
        raise SystemExit(
            f"refusing to run frozen seed {args.seed}: development and confirmation seeds are "
            "executable only by the authorised confirmatory run (mechsim.reproduce). "
            "Use a sentinel seed for a single-run diagnostic."
        )
    result = run_once(cfg, args.mechanism, args.seed, args.latency_ms)
    print(json.dumps(result.to_record(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
