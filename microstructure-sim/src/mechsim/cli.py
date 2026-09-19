"""Command line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contract import load_config
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
    p_run.add_argument("--seed", type=int, default=0)
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

    result = run_once(cfg, args.mechanism, args.seed, args.latency_ms)
    print(json.dumps(result.to_record(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
