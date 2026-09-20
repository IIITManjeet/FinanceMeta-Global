"""Guards on the outcome-blind smoke path and the confirmation seed set.

These exist because the previous `--quick` path executed the frozen mechanisms
on frozen seeds and printed a verdict. Nothing here should be relaxed.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest

from mechsim.contract import load_config
from mechsim.reproduce import SENTINEL_SEEDS, build_matrix, smoke


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_sentinel_seeds_touch_no_frozen_set(cfg) -> None:
    frozen = set(cfg.seeds) | set(cfg.confirmation_seeds)
    assert not (set(SENTINEL_SEEDS) & frozen)


def test_sentinel_seeds_are_obviously_not_frozen(cfg) -> None:
    assert all(s > 1_000_000 for s in SENTINEL_SEEDS)


def _smoke_body() -> ast.FunctionDef:
    """The smoke function with its docstring stripped, parsed for real."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(smoke)))
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef)
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        fn.body = fn.body[1:]
    return fn


def test_smoke_never_calls_the_decision_rule() -> None:
    called = {
        node.func.id
        for node in ast.walk(_smoke_body())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "decide" not in called, "the smoke path must not call the decision rule"


def test_smoke_never_writes_a_run_record_or_verdict() -> None:
    literals = {
        node.value
        for node in ast.walk(_smoke_body())
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    joined = " ".join(literals)
    for forbidden in ("runs.jsonl", "decision.json", "Verdict:"):
        assert forbidden not in joined, f"the smoke path must not produce {forbidden}"


def test_quick_mode_is_gone() -> None:
    src = Path(inspect.getsourcefile(smoke)).read_text(encoding="utf-8")
    assert '"--quick"' not in src and "args.quick" not in src


def test_smoke_runs_clean_and_writes_nothing(cfg, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert smoke(cfg) == 0
    assert list(tmp_path.iterdir()) == []


def test_confirmatory_matrix_uses_the_confirmation_seeds(cfg) -> None:
    seeds = {job[1] for job in build_matrix(cfg)}
    assert seeds == set(cfg.confirmation_seeds)


def test_confirmatory_matrix_excludes_the_exposed_seeds(cfg) -> None:
    seeds = {job[1] for job in build_matrix(cfg)}
    assert not (seeds & {0, 1, 2, 3, 4, 5})


def test_run_matrix_size_is_unchanged(cfg) -> None:
    """The recovery changed which seeds, not how many cells."""
    assert len(build_matrix(cfg)) == 540


def test_confirmation_set_is_thirty_disjoint_seeds(cfg) -> None:
    assert len(cfg.confirmation_seeds) == 30
    assert not (set(cfg.confirmation_seeds) & set(cfg.seeds))
