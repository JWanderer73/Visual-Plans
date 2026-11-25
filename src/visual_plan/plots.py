"""Generate standalone SVG plots from validated series."""

import base64
from io import BytesIO
from threading import Lock

from .text import axis_label

# Matplotlib's configuration and font handling are shared within the process.
_plot_lock = Lock()
COLORS = ["#205e82", "#a24a25", "#6f50a3", "#16725d", "#ad3762", "#525f79"]


def plot_image(example: dict) -> str:
    """Return a data URI for an SVG image isolated from the surrounding page."""
    with _plot_lock:
        svg = _render_svg(example)
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")


def _render_svg(example: dict) -> bytes:
    from matplotlib import rc_context
    from matplotlib.backends.backend_svg import FigureCanvasSVG
    from matplotlib.figure import Figure
    from matplotlib.ticker import ScalarFormatter

    series = example["series"]
    values = list(dict.fromkeys(point["x"] for item in series for point in item["points"]))
    categorical = isinstance(values[0], str)
    positions = {value: index for index, value in enumerate(values)} if categorical else {}
    if example["chart"] == "bar":
        numeric = sorted(positions.values() if categorical else values)
        spacing = min(
            (right - left for left, right in zip(numeric, numeric[1:])),
            default=max(1, abs(numeric[0]) * 0.1),
        )
        bar_width = 0.78 * spacing / len(series)

    with rc_context({
        "text.usetex": False,
        "text.parse_math": False,
        "svg.fonttype": "none",
        "svg.hashsalt": "visual-plan",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }):
        figure = Figure(figsize=(7.8, 4.1), layout="constrained", facecolor="#ffffff")
        ax = figure.subplots()
        handles = []
        for index, item in enumerate(series):
            x = [positions.get(point["x"], point["x"]) for point in item["points"]]
            y = [point["y"] for point in item["points"]]
            color = COLORS[index % len(COLORS)]
            if example["chart"] == "line":
                line, = ax.plot(x, y, marker="o", linewidth=2, color=color)
                handles.append(line)
            else:
                offset = (index - (len(series) - 1) / 2) * bar_width
                bars = ax.bar([value + offset for value in x], y, width=bar_width, color=color)
                handles.append(bars)

        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#e2e8f0")
        ax.set_xlabel(axis_label(example["x_axis"]))
        ax.set_ylabel(axis_label(example["y_axis"]))
        if categorical:
            longest = max(map(len, values))
            rotation = 35 if longest * len(values) > 70 else 0
            ax.set_xticks(list(positions.values()), values, rotation=rotation, ha="right" if rotation else "center")
        else:
            ax.xaxis.set_major_formatter(ScalarFormatter(useOffset=False))
        ax.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
        ax.legend(handles, [item["name"] for item in series], frameon=False)

        output = BytesIO()
        FigureCanvasSVG(figure).print_svg(output, metadata={"Date": None})
    return output.getvalue()
