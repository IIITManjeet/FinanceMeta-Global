"""The two reported artifacts that are not machine-readable output.

The contract requires a mechanism comparison table and a latency sensitivity
plot alongside the JSON. Neither was produced by anything, so both would have
been assembled by hand after the run, which puts a figure in front of a reviewer
that no committed code generates. That is the defect recorded as D13.

The plot is written as SVG built here rather than through a plotting library.
The environment is installed with hashed wheels only, so a new dependency would
mean re-pinning the lock and moving its digest for a chart; and text output
diffs, which suits a record meant to be checked rather than admired.
"""

from __future__ import annotations

from .mechanisms import FIFO, PRO_RATA


def _fmt(value: float | None, places: int = 4) -> str:
    """Trim trailing zeros without turning a small number into an exact zero."""
    if value is None:
        return "n/a"
    if value == 0.0:
        return "0"
    if abs(value) < 10 ** -places:
        return f"{value:.1e}"
    return f"{value:.{places}f}".rstrip("0").rstrip(".") or "0"


def comparison_table(summary: dict, metrics: tuple[str, ...],
                     not_differenced: frozenset[str] = frozenset()) -> str:
    """One table per metric: both arms at every latency, with the spread.

    Means alone are prohibited by the contract, so each cell carries the median
    with the 5th and 95th percentiles behind it.
    """
    cells = sorted({key.split("|")[0] for key in summary})
    lines = ["# Mechanism comparison", ""]

    for cell in cells:
        lines.append(f"## {cell} cell")
        lines.append("")
        latencies = sorted(
            {int(key.split("|")[1].removesuffix("ms")) for key in summary if key.startswith(f"{cell}|")}
        )
        for metric in metrics:
            lines.append(f"### {metric}")
            if metric in not_differenced:
                lines.append("")
                lines.append("Descriptive only. The arms measure this in different units, so it is "
                             "never differenced across mechanisms.")
            lines.append("")
            differenceable = metric not in not_differenced
            if differenceable:
                lines.append("| latency ms | FIFO median [p5, p95] | PRO_RATA median [p5, p95] "
                             "| difference of medians |")
                lines.append("| ---: | ---: | ---: | ---: |")
            else:
                # The arms measure this in different units, so the contract
                # forbids differencing it. Reporting it side by side is the
                # whole of what may be said.
                lines.append("| latency ms | FIFO median [p5, p95] | PRO_RATA median [p5, p95] |")
                lines.append("| ---: | ---: | ---: |")
            for latency in latencies:
                row = [str(latency)]
                medians: dict[str, float | None] = {}
                for mechanism in (FIFO, PRO_RATA):
                    stats = summary.get(f"{cell}|{latency}ms|{mechanism}", {}).get(metric)
                    if not stats:
                        medians[mechanism] = None
                        row.append("n/a")
                        continue
                    medians[mechanism] = stats["median"]
                    row.append(f"{_fmt(stats['median'])} [{_fmt(stats['p5'])}, {_fmt(stats['p95'])}]")
                if differenceable:
                    both = medians.get(FIFO), medians.get(PRO_RATA)
                    row.append(_fmt(both[1] - both[0]) if None not in both else "n/a")
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")

        lines.append("### retained runs")
        lines.append("")
        lines.append("| latency ms | mechanism | runs | with flags | flags |")
        lines.append("| ---: | --- | ---: | ---: | --- |")
        for latency in latencies:
            for mechanism in (FIFO, PRO_RATA):
                degenerate = summary.get(f"{cell}|{latency}ms|{mechanism}", {}).get("degenerate")
                if not degenerate:
                    continue
                flags = ", ".join(f"{k} {v}" for k, v in sorted(degenerate["flag_counts"].items())) or "none"
                lines.append(
                    f"| {latency} | {mechanism} | {degenerate['runs']} | {degenerate['with_flags']} | {flags} |"
                )
        lines.append("")

    lines.append("No run is excluded. An empty book, an unfilled parent and a timeout are")
    lines.append("retained results and are counted above.")
    lines.append("")
    return "\n".join(lines)


def latency_sensitivity_svg(summary: dict, metric: str, cell: str = "main",
                            not_differenced: frozenset[str] = frozenset()) -> str:
    """Difference of medians against latency for one metric, as a standalone SVG.

    The point of the sweep is whether a difference survives latency, so the
    series plotted is PRO_RATA minus FIFO rather than the two arms separately.
    A metric the contract forbids differencing therefore cannot be plotted here
    either. The table was taught that; this, its neighbour, was not.
    """
    if metric in not_differenced:
        raise ValueError(
            f"{metric} is not differenced across mechanisms, so it has no difference to plot"
        )
    points: list[tuple[int, float]] = []
    for key in summary:
        head, latency_text, mechanism = key.split("|")
        if head != cell or mechanism != FIFO:
            continue
        latency = int(latency_text.removesuffix("ms"))
        fifo = summary[key].get(metric)
        pro = summary.get(f"{cell}|{latency}ms|{PRO_RATA}", {}).get(metric)
        if not fifo or not pro or fifo["median"] is None or pro["median"] is None:
            continue
        points.append((latency, pro["median"] - fifo["median"]))
    points.sort()

    width, height = 720, 400
    left, right, top, bottom = 90, 30, 40, 60
    plot_w, plot_h = width - left - right, height - top - bottom

    if not points:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><text x="{width // 2}" y="{height // 2}" '
            f'text-anchor="middle" font-family="sans-serif" font-size="14">no paired cells to plot'
            f"</text></svg>\n"
        )

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys + [0.0]), max(ys + [0.0])
    if y_hi == y_lo:
        y_hi, y_lo = y_hi + 1.0, y_lo - 1.0
    if x_hi == x_lo:
        x_hi = x_lo + 1

    def sx(value: float) -> float:
        return left + (value - x_lo) / (x_hi - x_lo) * plot_w

    def sy(value: float) -> float:
        return top + (y_hi - value) / (y_hi - y_lo) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="24" font-size="15">Latency sensitivity: {metric}, PRO_RATA minus FIFO '
        f'({cell} cell)</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#333" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" '
        f'stroke="#333" stroke-width="1"/>',
    ]

    zero = sy(0.0)
    if top <= zero <= top + plot_h:
        parts.append(
            f'<line x1="{left}" y1="{zero:.1f}" x2="{left + plot_w}" y2="{zero:.1f}" '
            f'stroke="#999" stroke-width="1" stroke-dasharray="4 3"/>'
        )
        parts.append(f'<text x="{left - 8}" y="{zero + 4:.1f}" text-anchor="end" font-size="11">0</text>')

    for value in (y_lo, y_hi):
        parts.append(
            f'<text x="{left - 8}" y="{sy(value) + 4:.1f}" text-anchor="end" font-size="11">{_fmt(value, 3)}</text>'
        )

    path = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(points))
    parts.append(f'<path d="{path}" fill="none" stroke="#1f4e79" stroke-width="2"/>')

    for x, y in points:
        parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="3.5" fill="#1f4e79"/>')
        parts.append(
            f'<text x="{sx(x):.1f}" y="{top + plot_h + 18}" text-anchor="middle" font-size="11">{x}</text>'
        )

    parts.append(
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 18}" text-anchor="middle" font-size="12">'
        f"tracked agent one-way latency (ms)</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
