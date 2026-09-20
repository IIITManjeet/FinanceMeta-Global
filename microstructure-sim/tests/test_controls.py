"""The frozen controls: identity run, deterministic replay, zero-latency cell."""

from __future__ import annotations

import dataclasses
import json

import pytest

# Sentinel seeds only. Never a development seed (0-29) or a confirmation seed
# (100-129): a test run must not be able to produce an outcome on frozen data.
SENTINEL = (900_000_101, 900_000_102, 900_000_103, 900_000_104, 900_000_105)

from mechsim.contract import load_config
from mechsim.flow import generate_stream, stream_digest
from mechsim.mechanisms import FIFO, PRO_RATA
from mechsim.sim import run_once


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def probe(cfg):
    """A small but structurally identical configuration, for test speed."""
    return dataclasses.replace(cfg, warm_up_events=500, horizon_events=3000)


def test_identity_control_streams_match_across_mechanisms(probe) -> None:
    """Both arms must provably consume the same order-flow realization."""
    for seed in SENTINEL[:3]:
        a = stream_digest(generate_stream(probe, seed, 2000))
        b = stream_digest(generate_stream(probe, seed, 2000))
        assert a == b


def test_identity_control_holds_inside_full_runs(probe) -> None:
    fifo = run_once(probe, FIFO, seed=900_000_103, latency_ms=5)
    prorata = run_once(probe, PRO_RATA, seed=900_000_103, latency_ms=5)
    assert fifo.stream_sha256 == prorata.stream_sha256


def test_different_seeds_produce_different_streams(probe) -> None:
    digests = {stream_digest(generate_stream(probe, s, 2000)) for s in SENTINEL[:5]}
    assert len(digests) == 5


def test_deterministic_replay_is_byte_identical(probe) -> None:
    first = run_once(probe, FIFO, seed=900_000_107, latency_ms=5)
    second = run_once(probe, FIFO, seed=900_000_107, latency_ms=5)
    assert json.dumps(first.to_record(), sort_keys=True) == json.dumps(
        second.to_record(), sort_keys=True
    )


def test_deterministic_replay_holds_for_pro_rata(probe) -> None:
    first = run_once(probe, PRO_RATA, seed=900_000_111, latency_ms=25)
    second = run_once(probe, PRO_RATA, seed=900_000_111, latency_ms=25)
    assert first.to_record() == second.to_record()


def test_zero_latency_control_is_in_the_frozen_grid(cfg) -> None:
    assert 0 in cfg.latency_grid


def test_matched_baseline_is_on_the_frozen_grid(cfg) -> None:
    assert cfg.matched_baseline_ms in cfg.latency_grid


def test_frozen_seed_policy_is_thirty_seeds(cfg) -> None:
    assert cfg.seeds == tuple(range(30))


def test_run_record_carries_full_provenance(probe) -> None:
    record = run_once(probe, FIFO, seed=900_000_100, latency_ms=5).to_record()
    for key in ("mechanism", "seed", "latency_ms", "cell", "stream_sha256", "flags"):
        assert key in record
    assert len(record["stream_sha256"]) == 64
