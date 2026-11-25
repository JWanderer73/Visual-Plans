"""Validate the bundled schema and the relationships expressed in a plan."""

import json
import math
import re
from functools import cache
from graphlib import CycleError, TopologicalSorter
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

Plan = dict[str, Any]
INVALID_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


class PlanError(ValueError):
    """A plan cannot be parsed or validated."""


@cache
def _validator() -> Draft202012Validator:
    schema = files("visual_plan").joinpath("plan-v1.schema.json").read_text(encoding="utf-8")
    return Draft202012Validator(json.loads(schema))


def _location(plan: object, path: list) -> str:
    if not path:
        return "plan"
    location = ""
    for part in path:
        location += f"[{part}]" if isinstance(part, int) else f".{part}"
    location = location.lstrip(".")
    if len(path) >= 2 and path[0] == "steps" and isinstance(path[1], int):
        step = plan["steps"][path[1]]
        if isinstance(step, dict) and isinstance(step.get("id"), str):
            location += f" (step {step['id']!r})"
    return location


def _check_text_and_numbers(plan: Plan, value: object, path: list) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _check_text_and_numbers(plan, item, [*path, key])
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_text_and_numbers(plan, item, [*path, index])
    elif isinstance(value, str) and INVALID_TEXT.search(value):
        raise PlanError(f"{_location(plan, path)}: contains a character unsupported in HTML or SVG")
    elif isinstance(value, float) and not math.isfinite(value):
        raise PlanError(f"{_location(plan, path)}: must be a finite number")


def _check_plot(example: dict, plan: Plan, path: list) -> None:
    x_type = None
    for series_index, series in enumerate(example["series"]):
        seen_x = set()
        for point_index, point in enumerate(series["points"]):
            point_path = [*path, "series", series_index, "points", point_index]
            x = point["x"]
            current_type = "text" if isinstance(x, str) else "number"
            if x_type is not None and x_type != current_type:
                raise PlanError(f"{_location(plan, [*point_path, 'x'])}: plot x values must use one type")
            x_type = current_type
            if example["chart"] == "bar" and x in seen_x:
                raise PlanError(f"{_location(plan, [*point_path, 'x'])}: duplicate x value in a bar series")
            seen_x.add(x)
            for field in ("x", "y"):
                value = point[field]
                if isinstance(value, (int, float)) and abs(value) > 1e290:
                    raise PlanError(f"{_location(plan, [*point_path, field])}: value is outside the plotting range")


def _check_examples(owner: dict, plan: Plan, path: list) -> None:
    for index, example in enumerate(owner.get("examples", [])):
        example_path = [*path, "examples", index]
        match example["type"]:
            case "plot":
                _check_plot(example, plan, example_path)
            case "diagram":
                nodes = set()
                for node_index, node in enumerate(example["nodes"]):
                    if node["id"] in nodes:
                        field = _location(plan, [*example_path, "nodes", node_index, "id"])
                        raise PlanError(f"{field}: duplicate node ID {node['id']!r}")
                    nodes.add(node["id"])
                for edge_index, edge in enumerate(example["edges"]):
                    for endpoint in ("from", "to"):
                        if edge[endpoint] not in nodes:
                            field = _location(plan, [*example_path, "edges", edge_index, endpoint])
                            raise PlanError(f"{field}: unknown node ID {edge[endpoint]!r}")
            case "table":
                width = len(example["columns"])
                for row_index, row in enumerate(example["rows"]):
                    if len(row) != width:
                        field = _location(plan, [*example_path, "rows", row_index])
                        raise PlanError(f"{field}: expected {width} cells, found {len(row)}")


def validate_plan(value: object) -> Plan:
    """Return the validated plan in its original order, or raise PlanError."""
    errors = _validator().iter_errors(value)
    error = min(
        errors,
        key=lambda item: (item.validator == "unevaluatedProperties", len(item.absolute_path)),
        default=None,
    )
    if error is not None:
        field = _location(value, list(error.absolute_path))
        if list(error.absolute_path) == ["schema_version"]:
            raise PlanError(f"{field}: expected version 1, got {error.instance!r}")
        raise PlanError(f"{field}: {error.message}")

    plan = value
    _check_text_and_numbers(plan, plan, [])
    step_ids = set()
    for index, step in enumerate(plan["steps"]):
        if step["id"] in step_ids:
            field = _location(plan, ["steps", index, "id"])
            raise PlanError(f"{field}: duplicate step ID {step['id']!r}")
        step_ids.add(step["id"])

    graph = TopologicalSorter()
    for index, step in enumerate(plan["steps"]):
        for dependency_index, dependency in enumerate(step["depends_on"]):
            if dependency not in step_ids:
                field = _location(plan, ["steps", index, "depends_on", dependency_index])
                raise PlanError(f"{field}: unknown step ID {dependency!r}")
        graph.add(step["id"], *step["depends_on"])
    try:
        graph.prepare()
    except CycleError as error:
        cycle = " → ".join(repr(step_id) for step_id in error.args[1])
        raise PlanError(f"steps.depends_on: dependency cycle {cycle}") from error

    for index, decision in enumerate(plan.get("decisions", [])):
        if decision["step_id"] not in step_ids:
            raise PlanError(f"decisions[{index}].step_id: unknown step ID {decision['step_id']!r}")

    _check_examples(plan, plan, [])
    for index, step in enumerate(plan["steps"]):
        _check_examples(step, plan, ["steps", index])
    return plan


def _json_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise PlanError(f"duplicate JSON field {name!r}")
        result[name] = value
    return result


def load_plan(source: str) -> Plan:
    """Parse a JSON plan string and validate its contents."""
    try:
        value = json.loads(source, object_pairs_hook=_json_object)
    except json.JSONDecodeError as error:
        raise PlanError(f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from error
    except PlanError:
        raise
    except (ValueError, RecursionError) as error:
        raise PlanError(f"invalid JSON: {error}") from error
    return validate_plan(value)
