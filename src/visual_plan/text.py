"""Shared text representations and Markdown escaping."""

import json
import re
from html import escape


def axis_label(axis: dict) -> str:
    return f"{axis['label']} ({axis['unit']})" if "unit" in axis else axis["label"]


def cell_value(value: str | int | float | bool | None) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def plot_rows(example: dict) -> tuple[list[str], list[list]]:
    headers = ["Series", axis_label(example["x_axis"]), axis_label(example["y_axis"])]
    rows = [[item["name"], point["x"], point["y"]] for item in example["series"] for point in item["points"]]
    return headers, rows


def markdown_text(value: str, *, line_break: str = "<br>") -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    escaped = []
    for line in lines:
        text = escape(line.strip(), quote=False)
        text = re.sub(r"([\\`*_{}\[\]|~!$])", r"\\\1", text)
        text = re.sub(r"^([#+=:\-])", r"\\\1", text)
        text = re.sub(r"^(\d+)([.)])(?=\s|$)", r"\1\\\2", text)
        escaped.append(text)
    return line_break.join(escaped)


def markdown_table(headers: list[str], rows: list[list]) -> str:
    def row(values: list) -> str:
        return "| " + " | ".join(markdown_text(cell_value(value)) for value in values) + " |"

    separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    return "\n".join([row(headers), separator, *(row(values) for values in rows)])


def markdown_fence(text: str, language: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    separator = "" if text.endswith(("\n", "\r")) or not text else "\n"
    return f"{fence}{language}\n{text}{separator}{fence}"
