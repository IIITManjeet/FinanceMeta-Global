"""The two reported artifacts the contract requires beside the JSON.

Both would otherwise have been assembled by hand after the run, which is how a
figure no committed code produces reaches a reviewer. That is D13.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from mechsim.contract import load_config
from mechsim.mechanisms import FIFO, PRO_RATA
from mechsim.reporting import comparison_table, latency_sensitivity_svg

METRICS = ("fill_probability", "implementation_shortfall_bps")


def summary(pairs: dict[int, tuple[float, float]]) -> dict:
    """A summary block shaped like the one the run writes."""
    out: dict[str, dict] = {}
    for latency, (fifo, pro) in pairs.items():
        for mechanism, median in ((FIFO, fifo), (PRO_RATA, pro)):
            out[f"main|{latency}ms|{mechanism}"] = {
                metric: {"n": 30, "n_undefined": 0, "mean": median, "median": median,
                         "iqr": 0.5, "p5": median - 1, "p95": median + 1}
                for metric in METRICS
            }
            out[f"main|{latency}ms|{mechanism}"]["degenerate"] = {
                "runs": 30, "with_flags": 2, "flag_counts": {"empty_book": 2},
            }
    return out


def test_table_reports_both_arms_and_the_spread() -> None:
    text = comparison_table(summary({0: (1.0, 2.0), 5: (1.0, 3.0)}), METRICS)
    for metric in METRICS:
        assert metric in text
    assert "| 0 |" in text and "| 5 |" in text
    # medians alone are prohibited; the percentiles must travel with them
    assert "[0, 2]" in text or "[0, 2.0]" in text
    assert "1" in text and "2" in text


def test_table_reports_the_difference_between_arms() -> None:
    text = comparison_table(summary({5: (1.0, 3.5)}), METRICS)
    assert "2.5" in text


def test_table_counts_retained_runs_rather_than_dropping_them() -> None:
    text = comparison_table(summary({5: (1.0, 2.0)}), METRICS)
    assert "retained runs" in text
    assert "empty_book 2" in text
    assert "No run is excluded" in text


def test_table_marks_a_missing_arm_rather_than_inventing_one() -> None:
    data = summary({5: (1.0, 2.0)})
    del data[f"main|5ms|{PRO_RATA}"]
    text = comparison_table(data, METRICS)
    assert "n/a" in text


def test_plot_is_well_formed_svg_with_a_point_per_latency() -> None:
    svg = latency_sensitivity_svg(summary({0: (1.0, 1.0), 5: (1.0, 2.0), 25: (1.0, 4.0)}),
                                  "implementation_shortfall_bps")
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    circles = [e for e in root.iter() if e.tag.endswith("circle")]
    assert len(circles) == 3


def test_plot_series_is_the_difference_not_one_arm() -> None:
    """Both arms equal must put the series on zero, whatever their level."""
    flat = latency_sensitivity_svg(summary({0: (7.0, 7.0), 5: (9.0, 9.0)}), "implementation_shortfall_bps")
    ys = {e.get("cy") for e in ET.fromstring(flat).iter() if e.tag.endswith("circle")}
    assert len(ys) == 1


def test_plot_survives_having_nothing_to_draw() -> None:
    root = ET.fromstring(latency_sensitivity_svg({}, "implementation_shortfall_bps"))
    assert root.tag.endswith("svg")


def test_decision_metric_is_read_from_the_contract() -> None:
    """It was a literal in decide(), the same shape as D24 and D34."""
    import inspect

    from mechsim import analysis

    cfg = load_config()
    assert cfg.decision_metric_id == "implementation_shortfall_bps"
    source = inspect.getsource(analysis.decide)
    assert 'metric = "implementation_shortfall_bps"' not in source
    assert "cfg.decision_metric_id" in source


def test_the_record_carries_every_field_the_contract_requires() -> None:
    """The contract's list was only ever compared with another list.

    Nothing checked it against what the code emits, which is how a required
    field went missing from the freeze onwards without anything failing.
    """
    import json

    from mechsim.contract import DEFAULT_CONTRACT
    from mechsim.sim import run_once

    contract = json.loads(Path(DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    required = set(contract["reporting"]["required_run_fields"])
    record = run_once(load_config(), "FIFO", 900_000_001, 5).to_record()
    assert required <= set(record), sorted(required - set(record))


def test_the_run_writes_every_artifact_the_contract_declares(tmp_path) -> None:
    """The first version of this searched the source for each filename.

    Deleting the write and leaving the name in a comment passed it, which is
    the same vacuous shape as the defect it was meant to close. This calls the
    function the run uses and looks at what appears on disk.
    """
    import json

    from mechsim.contract import DEFAULT_CONTRACT
    from mechsim.reproduce import write_artifacts

    contract = json.loads(Path(DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    declared = [name for name in contract["reporting"]["artifacts"] if name != "runs.jsonl"]

    cfg = load_config()
    summary = {
        f"main|5ms|{mechanism}": {
            metric: {"n": 30, "n_undefined": 0, "mean": 1.0, "median": 1.0,
                     "iqr": 0.5, "p5": 0.5, "p95": 1.5}
            for metric in ("fill_probability", "implementation_shortfall_bps", "queue_measure")
        } | {"degenerate": {"runs": 30, "with_flags": 0, "flag_counts": {}}}
        for mechanism in ("FIFO", "PRO_RATA")
    }
    written = write_artifacts(
        tmp_path, cfg, Path(DEFAULT_CONTRACT), summary,
        {"verdict": "NULL"}, {"identity_control": "PASS"}, {"reviewer": "test"},
    )

    on_disk = {f.name for f in tmp_path.iterdir()}
    missing = [name for name in declared if name not in on_disk]
    assert not missing, missing
    assert set(written) == on_disk
    for name in declared:
        assert (tmp_path / name).stat().st_size > 0, f"{name} is empty"

    # runs.jsonl is written by the matrix loop itself, so it is the one
    # declared artifact this function does not produce
    assert "runs.jsonl" not in on_disk


def test_decide_follows_the_contract_metric_behaviourally() -> None:
    """A source-text check is walked past by splitting the literal in two.

    This varies the named metric instead and watches the statistic move, which
    a disguised hardcoded metric cannot satisfy.
    """
    import dataclasses

    from mechsim.analysis import decide

    cfg = load_config()
    seeds = tuple(900_000_400 + i for i in range(30))
    cells = [("main", latency) for latency in cfg.latency_grid]
    cells.append(("robustness", cfg.robustness_latency_ms))

    records = []
    for cell, latency in cells:
        for i, seed in enumerate(seeds):
            for mechanism, shortfall, impact in (("FIFO", 0.0, 0.0), ("PRO_RATA", 1.0, 50.0 + i)):
                records.append({
                    "mechanism": mechanism, "seed": seed, "latency_ms": latency, "cell": cell,
                    "implementation_shortfall_bps": shortfall, "price_impact_bps": impact,
                    "flags": [],
                })

    base = dataclasses.replace(cfg, confirmation_seeds=seeds)
    on_shortfall = decide(records, base)
    on_impact = decide(records, dataclasses.replace(base, decision_metric_id="price_impact_bps"))
    assert on_shortfall["point_estimate"] != on_impact["point_estimate"], (
        "the decision rule is not reading the contract's metric"
    )
    assert round(on_shortfall["point_estimate"], 6) == 1.0
    assert on_shortfall["metric"] == "implementation_shortfall_bps"
    assert on_impact["metric"] == "price_impact_bps"


def test_a_metric_the_contract_forbids_differencing_gets_no_difference_column() -> None:
    """The queue measure is lots under FIFO and a share under pro-rata.

    The contract says in terms that the two are never differenced. The
    delivered table subtracted one from the other, in an artifact written for
    the reviewer, because the fixture only covered metrics where differencing
    is valid.
    """
    import json

    from mechsim.contract import DEFAULT_CONTRACT

    contract = json.loads(Path(DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    forbidden = frozenset(contract["metrics"]["not_differenced_across_mechanisms"])
    assert "queue_measure" in forbidden

    data = {}
    for mechanism, median in (("FIFO", 12.0), ("PRO_RATA", 0.35)):
        data[f"main|5ms|{mechanism}"] = {
            "queue_measure": {"n": 30, "n_undefined": 0, "mean": median, "median": median,
                              "iqr": 1.0, "p5": median - 1, "p95": median + 1},
            "degenerate": {"runs": 30, "with_flags": 0, "flag_counts": {}},
        }

    text = comparison_table(data, ("queue_measure",), forbidden)
    assert "difference of medians" not in text
    assert "-11.65" not in text
    assert "never differenced across mechanisms" in text
    assert "12" in text and "0.35" in text

    # and a metric that may be differenced still is
    allowed = comparison_table(data, ("queue_measure",), frozenset())
    assert "difference of medians" in allowed


def test_the_plot_refuses_a_metric_that_may_not_be_differenced() -> None:
    """The table was taught this rule and its neighbour was not.

    Handing the plot the queue measure produced a chart titled PRO_RATA minus
    FIFO of lots against a fraction, the comparison the contract forbids.
    """
    import json

    import pytest

    from mechsim.contract import DEFAULT_CONTRACT

    contract = json.loads(Path(DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    forbidden = frozenset(contract["metrics"]["not_differenced_across_mechanisms"])

    data = summary({5: (1.0, 2.0)})
    with pytest.raises(ValueError, match="not differenced"):
        latency_sensitivity_svg(data, "queue_measure", not_differenced=forbidden)

    # the decision metric still plots
    svg = latency_sensitivity_svg(data, "implementation_shortfall_bps", not_differenced=forbidden)
    assert "<svg" in svg


def test_zero_formats_as_zero_whatever_its_sign() -> None:
    """-0.0 printed as -0, so an exact zero read as a small negative."""
    from mechsim.reporting import _fmt

    assert _fmt(0.0) == "0"
    assert _fmt(-0.0) == "0"
    assert _fmt(-0.0, 3) == "0"
    # and a genuinely small value is still not collapsed
    assert _fmt(1e-9) not in ("0", "-0")
    assert _fmt(-1e-9) not in ("0", "-0")
