"""Guards on the outcome-blind smoke path and the confirmation seed set.

These exist because the previous `--quick` path executed the frozen mechanisms
on frozen seeds and printed a verdict. Nothing here should be relaxed.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import mechsim.reproduce as R
import mechsim.sim as sim
from mechsim.contract import (
    CONTRACT_PATH_IN_REPO,
    DEFAULT_CONTRACT,
    committed_canonical_seeds,
    frozen_seeds,
    load_config,
)
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


def test_no_test_module_executes_a_frozen_seed(cfg) -> None:
    """Meta-guard. Tests run in CI, so a frozen seed here is an outcome leak.

    This is how development seeds 7 and 11 were exposed: the suite itself ran
    paired comparisons on them at the matched baseline.

    This scan is a backstop, not the primary defence. It only sees literals in
    the seed position, so an alias, a loop variable or a helper call walks past
    it. The real guard is the runtime check inside run_once.
    """
    frozen = set(cfg.seeds) | set(cfg.confirmation_seeds)
    offenders = []
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in {"run_once", "generate_stream", "stream_digest"}:
                continue
            # Only the seed position counts. Scanning every integer argument
            # treats latency_ms=5 as development seed 5.
            seed_arg = {"run_once": 2, "generate_stream": 1}.get(name)
            values = []
            if seed_arg is not None and len(node.args) > seed_arg:
                a = node.args[seed_arg]
                if isinstance(a, ast.Constant):
                    values.append(a.value)
            values += [k.value.value for k in node.keywords
                       if k.arg == "seed" and isinstance(k.value, ast.Constant)]
            # No exemption for allow_frozen_seed. The previous version of this
            # scanner whitelisted exactly that keyword, which is how a test
            # executing confirmation seed 100 passed the backstop unnoticed.
            for v in values:
                if isinstance(v, int) and v in frozen:
                    offenders.append(f"{path.name}:{node.lineno} -> seed {v}")
    assert not offenders, "tests must not execute frozen seeds: " + "; ".join(offenders)


def test_run_once_refuses_a_frozen_seed_at_runtime(cfg) -> None:
    """A runtime guard, not a lint rule. The AST scan can be walked around."""
    probe = dataclasses.replace(cfg, warm_up_events=50, horizon_events=100)
    for seed in (cfg.seeds[0], cfg.confirmation_seeds[0]):
        with pytest.raises(ValueError, match="refusing to run frozen seed"):
            sim.run_once(probe, "FIFO", seed, 5)


def test_frozen_seed_set_is_defined_by_identity_not_by_the_contract_passed(cfg, tmp_path) -> None:
    """--contract is an arbitrary path. A copy with empty seed lists used to unlock
    development seed 0 through the CLI and through run_once alike."""
    import mechsim.cli as cli

    doctored = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
    doctored["seed_policy"]["seeds"] = []
    doctored["seed_policy"]["confirmation_seeds"] = []
    copy = tmp_path / "experiment_contract.json"
    copy.write_text(json.dumps(doctored), encoding="utf-8")
    loose = load_config(copy)
    assert loose.seeds == () and loose.confirmation_seeds == ()

    assert frozen_seeds(loose) >= set(cfg.seeds) | set(cfg.confirmation_seeds)
    for seed in (cfg.seeds[0], cfg.confirmation_seeds[0]):
        with pytest.raises(ValueError, match="refusing to run frozen seed"):
            sim.run_once(loose, "FIFO", seed, 5)
        with pytest.raises(SystemExit, match="refusing to run frozen seed"):
            cli.main(["run", "--contract", str(copy), "--mechanism", "FIFO", "--seed", str(seed)])


def test_frozen_seed_set_fails_closed_without_the_canonical_contract(cfg, monkeypatch, tmp_path) -> None:
    import mechsim.contract as C
    monkeypatch.setattr(C, "DEFAULT_CONTRACT", tmp_path / "missing.json")
    with pytest.raises(OSError):
        frozen_seeds(cfg)
    with pytest.raises(OSError):
        sim._guard_frozen_seed(cfg, SENTINEL_SEEDS[0], False)


def test_frozen_seed_set_survives_an_in_place_edit_of_the_canonical_file(cfg, monkeypatch, tmp_path) -> None:
    """D19 moved one hop. The canonical file was the anchor, and nothing outside
    the receipt gate checked it against git, so editing it in place emptied the
    set and the guard let development seed 0 through. The committed copy at
    HEAD now contributes to the union. Shown at the guard function, which
    simulates nothing; a doctored Config never reaches run_once here."""
    import mechsim.contract as C

    doctored = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
    doctored["seed_policy"]["seeds"] = []
    doctored["seed_policy"]["confirmation_seeds"] = []
    edited = tmp_path / "experiment_contract.json"
    edited.write_text(json.dumps(doctored), encoding="utf-8")
    monkeypatch.setattr(C, "DEFAULT_CONTRACT", edited)
    loose = load_config(edited)
    assert loose.seeds == () and loose.confirmation_seeds == ()
    assert load_config(C.DEFAULT_CONTRACT).seeds == (), "the canonical anchor is the doctored file now"

    assert frozen_seeds(loose) >= set(cfg.seeds) | set(cfg.confirmation_seeds)
    for seed in (cfg.seeds[0], cfg.confirmation_seeds[0]):
        with pytest.raises(ValueError, match="refusing to run frozen seed"):
            sim._guard_frozen_seed(loose, seed, False)


def test_committed_seed_set_degrades_to_nothing_rather_than_blocking(cfg, tmp_path) -> None:
    """The committed copy is a contribution, not a gate: outside a checkout it
    contributes nothing and the on-disk union still protects every seed."""
    assert committed_canonical_seeds(tmp_path) == frozenset()
    assert committed_canonical_seeds() >= set(cfg.seeds) | set(cfg.confirmation_seeds)
    assert frozen_seeds(cfg) >= set(cfg.seeds) | set(cfg.confirmation_seeds)


def test_allow_frozen_seed_alone_is_inert(cfg) -> None:
    """The flag is one keyword away from any test. It is honoured only once a
    receipt has been validated in this process, so no scanner exemption exists."""
    assert not sim.AUTHORISED_CONTRACTS, "no receipt can have been validated in a test process"
    seed = cfg.confirmation_seeds[0]
    with pytest.raises(ValueError, match="honoured only after an authorisation receipt"):
        sim.run_once(cfg, "FIFO", seed, 5, allow_frozen_seed=True)
    with pytest.raises(ValueError, match="honoured only after an authorisation receipt"):
        sim._guard_frozen_seed(cfg, seed, True)
    with pytest.raises(ValueError, match="without allow_frozen_seed=True"):
        sim._guard_frozen_seed(cfg, seed, False)


def test_the_guard_admits_the_flag_only_with_the_grant(cfg, monkeypatch) -> None:
    """The guard function alone. It simulates nothing, so it is safe to show the
    accepting branch exists; run_once is never called here."""
    seed = cfg.confirmation_seeds[0]
    monkeypatch.setattr(sim, "AUTHORISED_CONTRACTS",
                        {(cfg.contract_id, cfg.contract_sha256, cfg.identity())})
    assert sim._guard_frozen_seed(cfg, seed, True) is None
    with pytest.raises(ValueError, match="without allow_frozen_seed=True"):
        sim._guard_frozen_seed(cfg, seed, False)
    monkeypatch.setattr(sim, "AUTHORISED_CONTRACTS",
                        {("some-other-contract", cfg.contract_sha256, cfg.identity())})
    with pytest.raises(ValueError, match="honoured only after"):
        sim._guard_frozen_seed(cfg, seed, True)


def test_grant_is_keyed_on_the_contract_bytes_not_the_id(cfg, monkeypatch, tmp_path) -> None:
    """The grant held contract ids, and the id is free text: any Config carrying
    it satisfied the guard whatever bytes it was loaded from. The key is now the
    id together with the sha256 of the bytes. Guard function only."""
    seed = cfg.confirmation_seeds[0]
    doctored = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
    doctored["negative_result_criteria"]["UNSTABLE"]["alpha"] = 0.9999
    copy = tmp_path / "experiment_contract.json"
    copy.write_text(json.dumps(doctored), encoding="utf-8")
    impostor = load_config(copy)
    assert impostor.contract_id == cfg.contract_id
    assert impostor.contract_sha256 != cfg.contract_sha256
    assert cfg.contract_sha256 == R.hashlib.sha256(DEFAULT_CONTRACT.read_bytes()).hexdigest()

    monkeypatch.setattr(sim, "AUTHORISED_CONTRACTS",
                        {(cfg.contract_id, cfg.contract_sha256, cfg.identity())})
    assert sim._guard_frozen_seed(cfg, seed, True) is None
    with pytest.raises(ValueError, match="honoured only after"):
        sim._guard_frozen_seed(impostor, seed, True)
    monkeypatch.setattr(sim, "AUTHORISED_CONTRACTS",
                        {(cfg.contract_id, "0" * 64, cfg.identity())})
    with pytest.raises(ValueError, match="honoured only after"):
        sim._guard_frozen_seed(cfg, seed, True)


def test_run_once_consults_the_guard_before_generating_a_stream() -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(sim.run_once)))
    calls = [_call_name(n) for n in ast.walk(tree) if isinstance(n, ast.Call)]
    calls = [c for c in calls if c in {"_guard_frozen_seed", "generate_stream"}]
    assert calls[:2] == ["_guard_frozen_seed", "generate_stream"]


def _call_name(node: ast.Call) -> str | None:
    return getattr(node.func, "id", None) or getattr(node.func, "attr", None)


def test_a_derived_configuration_does_not_inherit_the_grant(cfg, monkeypatch) -> None:
    """The grant used to key on two strings that dataclasses.replace copies.

    Config is frozen, which stops attribute assignment but not construction, so
    a derived configuration carried the contract id and file digest of the
    reviewed one while changing the scale, the horizon or the seeds. replace is
    used three times in this package, so this is ordinary code, not a trick.
    """
    import dataclasses

    from mechsim import sim

    monkeypatch.setattr(sim, "AUTHORISED_CONTRACTS",
                        {(cfg.contract_id, cfg.contract_sha256, cfg.identity())})
    sim._guard_frozen_seed(cfg, cfg.confirmation_seeds[0], True)

    for field, value in (("warm_up_events", 1), ("horizon_events", 2), ("parent_quantity", 999999)):
        derived = dataclasses.replace(cfg, **{field: value})
        assert derived.contract_id == cfg.contract_id
        assert derived.contract_sha256 == cfg.contract_sha256
        with pytest.raises(ValueError, match="has been validated"):
            sim._guard_frozen_seed(derived, cfg.confirmation_seeds[0], True)


def test_grant_is_mutated_only_by_the_authorisation_gate() -> None:
    """Whatever adds to AUTHORISED_CONTRACTS is the real authorisation. In the
    package that is one function; anything else would be a second gate.

    The name match is on ast.dump, which a concatenated or computed attribute
    name walks past, so the scan also refuses every route to a name that is
    not spelled out: getattr or setattr with a non-literal name, vars,
    globals, locals, __dict__, exec and eval. The package uses none of them,
    and a use appearing is itself the finding.
    """
    src = Path(inspect.getsourcefile(smoke)).parent
    offenders = []
    dynamic = []
    for path in sorted(src.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        enclosing: dict[ast.AST, ast.FunctionDef | None] = {}
        for parent in ast.walk(tree):
            owner = parent if isinstance(parent, ast.FunctionDef) else enclosing.get(parent)
            for child in ast.iter_child_nodes(parent):
                enclosing[child] = owner
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"getattr", "setattr", "delattr"}:
                if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
                    dynamic.append(f"{path.name}:{node.lineno} {node.func.id} with a computed name")
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"vars", "globals", "locals", "exec", "eval"}:
                dynamic.append(f"{path.name}:{node.lineno} {node.func.id}()")
            if isinstance(node, ast.Attribute) and node.attr == "__dict__":
                dynamic.append(f"{path.name}:{node.lineno} __dict__")
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) in {"add", "update", "__ior__"}:
                touched = "AUTHORISED_CONTRACTS" in ast.dump(node.func.value)
            elif isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                touched = any("AUTHORISED_CONTRACTS" in ast.dump(t) for t in targets)
            else:
                continue
            if not touched:
                continue
            owner = enclosing.get(node)
            definition = path.name == "sim.py" and owner is None and isinstance(node, ast.Assign)
            gate = path.name == "reproduce.py" and owner is not None and owner.name == "_require_authorisation"
            if not (definition or gate):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, "only _require_authorisation may grant frozen seeds: " + "; ".join(offenders)
    assert not dynamic, "no computed attribute access in the package, so the scan above cannot be walked past: " + "; ".join(dynamic)


def test_latency_grid_comes_from_the_contract(cfg) -> None:
    """Nothing asserted build_matrix enumerates cfg.latency_grid rather than a
    literal list of the same eight numbers; an equality check on the default
    grid would pass either. Move the grid and the matrix has to follow."""
    moved = dataclasses.replace(cfg, latency_grid=(3, 7, 11))
    main = {job[2] for job in build_matrix(moved) if job[3] == "main"}
    assert main == {3, 7, 11}
    assert len([job for job in build_matrix(moved) if job[3] == "main"]) == 2 * 3 * len(cfg.confirmation_seeds)


def test_robustness_latency_comes_from_the_contract(cfg) -> None:
    """It coincided with the baseline by accident; nothing tied them together."""
    from mechsim.reproduce import build_matrix
    latencies = {job[2] for job in build_matrix(cfg) if job[3] == "robustness"}
    assert latencies == {cfg.robustness_latency_ms}


def test_robustness_distribution_comes_from_the_contract(cfg) -> None:
    """A code literal that matched the contract's prose, and nothing tying them."""
    contract = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
    assert cfg.robustness_size_distribution == contract["robustness_cell"]["order_size_distribution_lots"] == {"1": 1.0}
    assert not hasattr(R, "CONSTANT_SIZE_DISTRIBUTION")
    # a literal equal to the contract would pass an equality check, so the
    # binding is shown by moving the contract value and watching the matrix follow
    moved = dataclasses.replace(cfg, robustness_size_distribution={"2": 1.0})
    dists = {json.dumps(job[4], sort_keys=True) for job in build_matrix(moved) if job[3] == "robustness"}
    assert dists == {json.dumps({"2": 1.0}, sort_keys=True)}
    assert all(job[4] is None for job in build_matrix(moved) if job[3] == "main")


def test_book_is_built_with_the_contract_floor() -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(sim.run_once)))
    books = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "Book"]
    assert len(books) == 1
    floor = next(k.value for k in books[0].keywords if k.arg == "min_allocation_lots")
    assert isinstance(floor, ast.Attribute) and floor.attr == "min_allocation_lots"


def test_confirmatory_run_refuses_without_an_authorisation_receipt(cfg, tmp_path) -> None:
    """Authorisation lives in a receipt, so granting it never edits the contract."""
    with pytest.raises(SystemExit, match="no authorisation receipt"):
        R.main(["--out", str(tmp_path / "results")])
    assert not (tmp_path / "results").exists(), "no output may be created before authorisation"


def test_the_authorisation_gate_is_the_first_thing_main_does() -> None:
    """A gate that returns instead of raising starts the real run, and a test that
    only asserts SystemExit would not notice until the matrix was executing. This
    pins the shape instead: nothing but argument parsing, configuration loading
    and the smoke branch may precede the gate, nothing may wrap it in a try, and
    the runtime gate, the output directory, the controls, the matrix and every
    run_once come after it. It parses main; it never calls it.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(R.main)))
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef)
    assert not any(isinstance(n, ast.Try) for n in ast.walk(fn)), "nothing may catch the gate's refusal"

    ordered = sorted((n for n in ast.walk(fn) if isinstance(n, ast.Call)), key=lambda n: (n.lineno, n.col_offset))
    names = [_call_name(n) for n in ordered]
    assert "_require_authorisation" in names, "the authorisation gate has been removed from main"
    gate = names.index("_require_authorisation")
    allowed_before = {"ArgumentParser", "add_argument", "parse_args", "Path", "load_config", "smoke"}
    assert set(names[:gate]) <= allowed_before, names[:gate]
    for later in ("_require_locked_runtime", "mkdir", "verify_controls", "build_matrix", "run_once", "decide"):
        assert later in names[gate + 1:], f"{later} must come after the gate"

    # the gate's result is kept, so a gate rewritten to return None is visible
    stmt = next(n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Call) and _call_name(n.value) == "_require_authorisation")
    assert stmt.targets[0].id == "authorisation"


def test_runtime_gate_rejects_a_drifted_environment(cfg, monkeypatch) -> None:
    """Hashing the lock file proves nothing about site-packages."""
    real = R.metadata.version
    monkeypatch.setattr(R.metadata, "version",
                        lambda n: "99.0.0" if n == "numpy" else real(n))
    with pytest.raises(SystemExit, match="does not match the lock"):
        R._require_locked_runtime(cfg, Path(DEFAULT_CONTRACT))


def test_cli_cannot_unlock_a_frozen_seed(cfg) -> None:
    """The CLI had an override that let a frozen outcome be produced before
    authorisation, and a confirmation seed inspected individually. It is gone:
    frozen outcomes are reachable only through the authorised confirmatory run."""
    import mechsim.cli as cli

    src = inspect.getsource(cli.main)
    assert "i_am_authorised_to_run_a_frozen_seed" not in src, "the CLI override must not come back"
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "run_once":
            assert not any(k.arg == "allow_frozen_seed" for k in node.keywords), (
                "cli run must never pass allow_frozen_seed"
            )

    for seed in (cfg.seeds[0], cfg.confirmation_seeds[0]):
        with pytest.raises(SystemExit, match="refusing to run frozen seed"):
            cli.main(["run", "--mechanism", "FIFO", "--seed", str(seed)])


def test_authorisation_predicate_rejects_near_miss_receipts(cfg, tmp_path) -> None:
    """A prefix test would have accepted AUTHORIZED_REVOKED; the predicate is an exact bool.

    Refused before the gate consults git, so a staged copy is enough here."""
    contract = json.loads(Path(DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    staged = tmp_path / "experiment_contract.json"
    staged.write_text(json.dumps(contract), encoding="utf-8")
    receipt = tmp_path / "authorization.json"

    base = {"contract_id": contract["contract_id"], "reviewed_sha": "0" * 40,
            "reviewer": "x", "timestamp_utc": "t"}
    for approved in ("AUTHORIZED", "AUTHORIZED_REVOKED", "true", 1, None):
        receipt.write_text(json.dumps({**base, "approved": approved}), encoding="utf-8")
        with pytest.raises(SystemExit, match="does not approve"):
            R._require_authorisation(staged)



# ---------------------------------------------------------------------------
# The receipt gate proves things about a git repository, so it is exercised
# against a throwaway one built here: the contract at its canonical path, a copy
# of this package, one commit, the freeze tag. Earlier versions of these tests
# created and deleted a tag in whatever repository pytest happened to run in,
# which leaked if the run was killed. The gate itself runs in a subprocess so
# that the package it finds is the copy inside the throwaway worktree.

GATE_SCRIPT = """
import json, sys
from pathlib import Path
import mechsim
from mechsim import sim
from mechsim.reproduce import _require_authorisation
record = _require_authorisation(Path(sys.argv[1]))
print("RECORD " + json.dumps({"record": record, "granted": sorted(sim.AUTHORISED_CONTRACTS),
                              "package": str(Path(mechsim.__file__).resolve())}))
"""


class GateRepo:
    def __init__(self, root: Path, tag: bool = True) -> None:
        self.root = root
        self.contract = root / CONTRACT_PATH_IN_REPO
        self.receipt = self.contract.parent / "authorization.json"
        self.package = root / "microstructure-sim/src/mechsim"
        self.package.mkdir(parents=True)
        self.contract.parent.mkdir(parents=True)
        shutil.copyfile(DEFAULT_CONTRACT, self.contract)
        for source in Path(inspect.getsourcefile(smoke)).parent.glob("*.py"):
            shutil.copyfile(source, self.package / source.name)
        # the real repository ignores caches, which is what makes a planted
        # .pyc invisible to git status; without this the fixture would be
        # kinder than reality and the bytecode check would look unnecessary.
        (root / ".gitignore").write_text("__pycache__/\n*.py[cod]\n", encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        # in the repository config, not just on our own invocations: the gate
        # shells out to git itself and must see the same line-ending rules.
        self.git("config", "core.autocrlf", "false")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "reviewed source")
        self.head = self.git("rev-parse", "HEAD")
        data = json.loads(self.contract.read_bytes())
        self.contract_id = data["contract_id"]
        self.freeze_tag = data["authority"]["freeze_tag"]
        if tag:
            self.git("tag", "-a", self.freeze_tag, "-m", "reviewed")

    def git(self, *args: str) -> str:
        identity = ["-c", "user.name=gate test", "-c", "user.email=gate@test.invalid",
                    "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", "-c", "core.autocrlf=false"]
        done = subprocess.run(["git", "-C", str(self.root), *identity, *args],
                              capture_output=True, text=True, check=True)
        return done.stdout.strip()

    def body(self, **overrides) -> dict:
        base = {"approved": True, "contract_id": self.contract_id, "reviewed_sha": self.head,
                "reviewed_tag": self.freeze_tag, "reviewer": "pre-run reviewer",
                "timestamp_utc": "2026-09-21T00:00:00Z"}
        return {**base, **overrides}

    def gate(self, receipt: dict | None, package_root: Path | None = None, cwd: Path | None = None):
        """Run the gate on this repository's contract. Returns (returncode, stdout, stderr)."""
        if receipt is None:
            if self.receipt.exists():
                self.receipt.unlink()
        else:
            self.receipt.write_text(json.dumps(receipt), encoding="utf-8")
        src = (package_root or self.root) / "microstructure-sim/src"
        env = {**os.environ, "PYTHONPATH": str(src), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
        done = subprocess.run([sys.executable, "-B", "-c", GATE_SCRIPT, str(self.contract)],
                              capture_output=True, text=True, env=env, cwd=str(cwd or self.root.parent))
        return done.returncode, done.stdout, done.stderr

    def accepts(self, receipt: dict | None, **kwargs) -> None:
        code, out, err = self.gate(receipt, **kwargs)
        assert code == 0, err
        assert "RECORD" in out

    def refuses(self, receipt: dict | None, phrase: str, **kwargs) -> None:
        code, out, err = self.gate(receipt, **kwargs)
        assert code != 0, f"gate accepted: {out}"
        assert phrase in err, f"expected {phrase!r} in refusal, got: {err}"
        assert "RECORD" not in out


@pytest.fixture
def repo(tmp_path) -> GateRepo:
    return GateRepo(tmp_path / "worktree")


def test_receipt_must_name_the_freeze_tag_and_it_must_be_a_tag(tmp_path) -> None:
    """HEAD, a branch name and a short SHA used to satisfy the tag cross-check."""
    untagged = GateRepo(tmp_path / "worktree", tag=False)
    untagged.refuses(untagged.body(reviewed_tag=""), "must name the reviewed tag")
    for not_a_tag in ("HEAD", "main", untagged.head[:12], "refs/heads/main"):
        untagged.refuses(untagged.body(reviewed_tag=not_a_tag), "this contract's freeze tag is")
    # a branch carrying the freeze tag's name is still not the tag
    untagged.git("branch", untagged.freeze_tag)
    untagged.refuses(untagged.body(), "does not resolve here as a tag")


def test_receipt_tag_and_sha_must_agree(repo) -> None:
    repo.refuses(repo.body(reviewed_sha="0" * 40), "internally inconsistent")
    repo.git("tag", "-a", "other-tag", "-m", "x")
    repo.refuses(repo.body(reviewed_tag="other-tag"), "this contract's freeze tag is")


def test_receipt_must_name_head_exactly_not_an_ancestor(repo) -> None:
    """Any number of unreviewed commits after the reviewed one used to pass."""
    (repo.package / "analysis.py").write_text(
        (repo.package / "analysis.py").read_text(encoding="utf-8") + "\n# a change after review\n",
        encoding="utf-8")
    repo.git("commit", "-q", "-am", "unreviewed change")
    assert repo.git("rev-parse", "HEAD") != repo.head
    repo.refuses(repo.body(), "needs a fresh one")


def test_gate_refuses_a_dirty_worktree(repo) -> None:
    """Uncommitted edits to the decision rule passed with reviewed_sha == HEAD."""
    edited = repo.package / "analysis.py"
    edited.write_text(edited.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    repo.refuses(repo.body(), "Differing paths")
    code, out, err = repo.gate(repo.body())
    assert "microstructure-sim/src/mechsim/analysis.py" in err
    repo.git("checkout", "--", "microstructure-sim/src/mechsim/analysis.py")

    stray = repo.root / "conftest.py"
    stray.write_text("# untracked\n", encoding="utf-8")
    code, out, err = repo.gate(repo.body())
    assert code != 0 and "conftest.py" in err and "Untracked paths" in err
    stray.unlink()

    # the receipt itself is the one file allowed to differ
    code, out, err = repo.gate(repo.body())
    assert code == 0, err


def test_gate_hashes_every_tracked_file_against_the_reviewed_tree(repo) -> None:
    """git status trusts the index, and update-index --skip-worktree or
    --assume-unchanged makes it report a modified file as clean. An audit hid
    edits to the decision rule and the mechanisms that way, hollowed out the
    gate, and had a receipt for a nonexistent contract accepted. The gate now
    hashes the bytes on disk against the blob ids in the reviewed tree, which
    the index cannot influence, and a deleted file is caught the same way."""
    analysis = "microstructure-sim/src/mechsim/analysis.py"
    mechanisms = "microstructure-sim/src/mechsim/mechanisms.py"
    reproduce = "microstructure-sim/src/mechsim/reproduce.py"
    for rel, flag in ((analysis, "--skip-worktree"), (mechanisms, "--assume-unchanged")):
        path = repo.root / rel
        # bytes, not text: mechanisms.py has no "cfg." to replace, so the edit
        # was a no-op and this half only passed because writing text back
        # rewrote LF as CRLF on Windows, which left --assume-unchanged untested.
        before = path.read_bytes()
        path.write_bytes(before + b"\n# edited after review\n")
        assert path.read_bytes() != before
        repo.git("update-index", flag, rel)
    assert repo.git("status", "--porcelain", "--untracked-files=no") == "", "the index must be hiding both edits"
    repo.refuses(repo.body(), "not the bytes committed at")
    code, out, err = repo.gate(repo.body())
    assert analysis in err and mechanisms in err, err
    assert reproduce not in err
    for rel, flag in ((analysis, "--no-skip-worktree"), (mechanisms, "--no-assume-unchanged")):
        repo.git("update-index", flag, rel)
        repo.git("checkout", "--", rel)

    # an edit to the gate's own module, away from the gate, is caught too
    path = repo.root / reproduce
    path.write_bytes(path.read_bytes() + b"\n# after review\n")
    repo.git("update-index", "--skip-worktree", reproduce)
    assert repo.git("status", "--porcelain", "--untracked-files=no") == ""
    code, out, err = repo.gate(repo.body())
    assert code != 0 and reproduce in err
    repo.git("update-index", "--no-skip-worktree", reproduce)
    repo.git("checkout", "--", reproduce)

    # a tracked file removed from disk with the index told to ignore it
    missing = "microstructure-sim/src/mechsim/diagnostics.py"
    repo.git("update-index", "--skip-worktree", missing)
    (repo.root / missing).unlink()
    assert repo.git("status", "--porcelain", "--untracked-files=no") == ""
    code, out, err = repo.gate(repo.body())
    assert code != 0 and f"{missing} (missing)" in err
    repo.git("update-index", "--no-skip-worktree", missing)
    repo.git("checkout", "--", missing)

    code, out, err = repo.gate(repo.body())
    assert code == 0, err


def test_disk_hashing_asks_git_rather_than_hashing_raw_bytes(repo) -> None:
    """Raw byte hashing called every file drift on a checkout that stores CRLF.

    The committed blobs are LF, and a checkout configured to convert line
    endings writes CRLF, so the file differs byte for byte while being exactly
    what git would record; the gate refused every file on such a checkout. The
    walk asks git for the object id it would store, so the comparison matches
    git's own view wherever it runs. It reads the file and not the index, so
    the skip-worktree tampering this walk exists to catch is unaffected, which
    the tests above cover.
    """
    import subprocess

    import mechsim.reproduce as R

    rels = ["microstructure-sim/src/mechsim/analysis.py",
            "microstructure-sim/src/mechsim/mechanisms.py",
            "evaluation/microstructure-mechanism-2026-09/experiment_contract.json"]
    expected = subprocess.run(["git", "hash-object", "--", *rels], cwd=repo.root,
                              capture_output=True, text=True, check=True).stdout.split()
    assert R._disk_blob_ids(repo.root, rels) == dict(zip(rels, expected))

    # and a real content change is still drift, whatever the line endings
    target = repo.root / rels[0]
    original = target.read_bytes()
    target.write_bytes(original + b"\n# changed\n")
    try:
        drift, _tracked = R._tree_drift(repo.head, repo.root)
        assert rels[0] in drift
    finally:
        target.write_bytes(original)
    drift, _tracked = R._tree_drift(repo.head, repo.root)
    assert not drift


def test_gate_refuses_bytecode_the_reviewed_tree_does_not_contain(repo) -> None:
    """Verifying source proves what the .py files say, not what the interpreter runs.

    Python prefers a cached .pyc whose header matches its source, and
    __pycache__ is untracked and ignored, so the gate's own git status call
    reports nothing for it. Bytecode planted there runs in place of source that
    still hashes correctly, which leaves the reviewed bytes and the executed
    bytes different while every check reports OK.
    """
    import mechsim.reproduce as R

    repo.accepts(repo.body())

    cache = repo.root / "microstructure-sim/src/mechsim/__pycache__"
    cache.mkdir(parents=True, exist_ok=True)
    planted = cache / "analysis.cpython-312.pyc"
    planted.write_bytes(b"\x00" * 32)
    try:
        status = repo.git("status", "--porcelain", "--untracked-files=all")
        assert "__pycache__" not in status, (
            "git hides ignored paths, which is why this needs checking another way"
        )
        drift, tracked = R._tree_drift(repo.head, repo.root)
        assert not drift, "no tracked file changed"
        assert "microstructure-sim/src/mechsim/__pycache__/analysis.cpython-312.pyc" in (
            R._foreign_importable(repo.root, tracked)
        )
        repo.refuses(repo.body(), "the reviewed tree does not contain")
    finally:
        planted.unlink()

    repo.accepts(repo.body())


def test_a_stray_module_on_the_import_path_is_refused(repo) -> None:
    """A file that shadows nothing today can shadow something tomorrow."""
    import mechsim.reproduce as R

    stray = repo.root / "microstructure-sim/src/mechsim/sitecustomize.py"
    stray.write_bytes(b"# not reviewed\n")
    try:
        _drift, tracked = R._tree_drift(repo.head, repo.root)
        assert "microstructure-sim/src/mechsim/sitecustomize.py" in R._foreign_importable(repo.root, tracked)
        # a plain .py is untracked rather than ignored, so the untracked check
        # reaches it first; either refusal names the path, which is the point
        code, _out, err = repo.gate(repo.body())
        assert code != 0 and "sitecustomize.py" in err
    finally:
        stray.unlink()


def test_gate_refuses_a_contract_whose_bytes_differ_from_the_reviewed_blob(repo) -> None:
    """A doctored copy with the same contract_id was accepted and loaded. Hiding the
    edit from git status with skip-worktree is exactly the case the byte comparison
    has to catch on its own."""
    doctored = json.loads(repo.contract.read_bytes())
    doctored["negative_result_criteria"]["UNSTABLE"]["alpha"] = 0.9999
    doctored["latency"]["matched_baseline_ms"] = 999999
    repo.git("update-index", "--skip-worktree", CONTRACT_PATH_IN_REPO)
    repo.contract.write_bytes(json.dumps(doctored, indent=2).encode("utf-8") + b"\n")
    assert repo.git("status", "--porcelain") == ""
    repo.refuses(repo.body(), "not byte-identical")


def test_gate_refuses_a_contract_away_from_its_canonical_path(repo) -> None:
    elsewhere = repo.root / "evaluation/copy/experiment_contract.json"
    elsewhere.parent.mkdir(parents=True)
    shutil.copyfile(repo.contract, elsewhere)
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")
    repo.git("tag", "-f", "-a", repo.freeze_tag, "-m", "reviewed")
    repo.head = repo.git("rev-parse", "HEAD")
    repo.contract, canonical = elsewhere, repo.contract
    repo.receipt = elsewhere.parent / "authorization.json"
    repo.refuses(repo.body(), "not the reviewed document at")
    # the stray receipt beside the copy is itself an untracked file, so it has
    # to go before the canonical document can be accepted
    repo.receipt.unlink()
    repo.contract, repo.receipt = canonical, canonical.parent / "authorization.json"
    code, out, err = repo.gate(repo.body())
    assert code == 0, err


def test_gate_refuses_a_package_that_is_not_the_reviewed_copy(repo) -> None:
    """A clean tree says nothing about which copy of the package is running.

    Requiring only that the executing file sit somewhere inside the worktree
    was not enough: a second copy under an ignored directory, or one reached
    through a .pth file or PYTHONPATH that no review covers, satisfied that
    while running bytes nobody read.
    """
    real_repo = Path(inspect.getsourcefile(smoke)).resolve().parents[3]
    repo.refuses(repo.body(), "not the reviewed copy", package_root=real_repo)

    # a full second copy inside the worktree, under a directory git ignores
    shadow = repo.root / "microstructure-sim/build/lib/mechsim"
    shadow.mkdir(parents=True)
    for source in (repo.root / "microstructure-sim/src/mechsim").glob("*.py"):
        (shadow / source.name).write_bytes(source.read_bytes())
    (repo.root / ".gitignore").write_text("__pycache__/\n*.py[cod]\nbuild/\n", encoding="utf-8")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "ignore build")
    repo.git("tag", "-f", "-a", repo.freeze_tag, "-m", "reviewed")
    repo.head = repo.git("rev-parse", "HEAD")
    try:
        assert repo.git("status", "--porcelain", "--untracked-files=all") == ""
        repo.refuses(repo.body(), "not the reviewed copy",
                     package_root=repo.root / "microstructure-sim/build")
    finally:
        for f in shadow.glob("*.py"):
            f.unlink()


def test_a_well_formed_receipt_is_accepted_and_recorded(repo) -> None:
    """Every other receipt test asserts a refusal, which a gate wired shut would also pass.

    This one pins the other direction: a receipt naming this contract, this
    revision and the freeze tag pointing at it is accepted, the record handed
    back carries what the contract says a run must report, and the grant that
    lets run_once honour allow_frozen_seed appears only then. It evaluates the
    gate only, in a subprocess; no seed is exercised and no outcome is produced.
    """
    body = repo.body()
    code, out, err = repo.gate(body, cwd=repo.root.parent)
    assert code == 0, err
    payload = json.loads(out.splitlines()[-1].removeprefix("RECORD "))
    record = payload["record"]

    assert record["reviewed_sha"] == repo.head
    assert record["reviewed_tag"] == repo.freeze_tag
    assert record["head_sha"] == repo.head
    assert record["reviewer"] == "pre-run reviewer"
    assert record["granted_utc"] == body["timestamp_utc"]
    assert record["receipt_sha256"] == R.hashlib.sha256(repo.receipt.read_bytes()).hexdigest()
    granted, = payload["granted"]
    assert granted[:2] == [repo.contract_id,
                           R.hashlib.sha256(repo.contract.read_bytes()).hexdigest()]
    # the third element binds the grant to the configuration those bytes produce,
    # so a configuration derived with dataclasses.replace does not inherit it
    assert granted[2] == R.load_config(repo.contract).identity()
    assert Path(payload["package"]).is_relative_to(repo.root.resolve())

    contract = json.loads(repo.contract.read_bytes())
    assert set(contract["authorization"]["run_records"]) <= set(record)
    assert "OK" in out

    # the process running this test has validated nothing
    assert not sim.AUTHORISED_CONTRACTS


def test_the_committed_seed_read_is_always_fresh(tmp_path) -> None:
    """A cache here would have to be right about when it is wrong.

    The first attempt at this stored the result on first use, which meant a
    transient git failure could be remembered as an answer. The store turned
    out to be unreachable anyway, because the success path returned from inside
    the try, so nothing was ever cached and the test written for it passed
    vacuously. Reading fresh every time is what the code does and what it
    should do, so that is what is pinned.
    """
    from mechsim import contract as C

    assert not hasattr(C, "_COMMITTED_SEEDS"), "no cache to go stale"
    assert not hasattr(C.committed_canonical_seeds, "cache_info"), "and not an lru_cache either"

    real = C.committed_canonical_seeds(C.REPO_ROOT)
    assert real, "the repository has a committed contract to read"
    assert C.committed_canonical_seeds(C.REPO_ROOT) == real

    # no git here, so it contributes nothing rather than blocking
    assert C.committed_canonical_seeds(tmp_path) == frozenset()
    # and that failure does not affect the next real read
    assert C.committed_canonical_seeds(C.REPO_ROOT) == real
