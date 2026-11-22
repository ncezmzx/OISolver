"""Declarative adapters from common OI inputs to V2 structural shrinkers.

The adapter deliberately supports a small, explicit schema rather than guessing a
statement format.  Every rendered proposal is still accepted only by the caller's
problem validator and candidate/oracle mismatch check.
"""
from dataclasses import dataclass
import hashlib
import math
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .domain_shrinkers import DomainShrinkError, shrink_domain


class InputAdapterError(ValueError):
    pass


Attempt = Callable[[bytes, str], bool]
CanAttempt = Callable[[], bool]


@dataclass
class AdaptedCase:
    kind: str
    header: Dict[str, int]
    node_weights: Optional[List[int]] = None
    edges: Optional[List[Dict[str, int]]] = None
    operations: Optional[List[List[str]]] = None
    initial: Optional[List[int]] = None
    grid: Optional[List[List[str]]] = None


def _positive_int(value: Any, label: str, allow_zero: bool = False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise InputAdapterError("{} must be {} integer".format(
            label, "a nonnegative" if allow_zero else "a positive"
        ))
    return value


def _string_list(value: Any, label: str, nonempty: bool = True) -> List[str]:
    if (not isinstance(value, list) or (nonempty and not value)
            or any(not isinstance(item, str) or not item for item in value)
            or len(value) != len(set(value))):
        raise InputAdapterError("{} must be a{} unique string array".format(
            label, " nonempty" if nonempty else ""
        ))
    return list(value)


def _header_fields(spec: Dict[str, Any]) -> List[str]:
    return _string_list(spec.get("header_fields"), "case.header_fields")


def _field(spec: Dict[str, Any], name: str, fields: Sequence[str]) -> str:
    value = spec.get(name)
    if not isinstance(value, str) or value not in fields:
        raise InputAdapterError("case.{} must name a header field".format(name))
    return value


def _index_base(spec: Dict[str, Any]) -> int:
    value = spec.get("index_base", 1)
    if type(value) is not int or value not in (0, 1):
        raise InputAdapterError("case.index_base must be 0 or 1")
    return value


def _reject_unknown(value: Dict[str, Any], allowed: Sequence[str], label: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise InputAdapterError("{} has unknown fields: {}".format(
            label, ", ".join(unknown)
        ))


def validate_adapter_schema(schema: Dict[str, Any]) -> None:
    """Validate the complete declarative schema and reject silent typo fields."""
    if not isinstance(schema, dict) or schema.get("schema_version") != 1:
        raise InputAdapterError("adapter requires schema_version 1")
    _reject_unknown(schema, ("schema_version", "test_cases", "case"), "adapter")
    test_cases = schema.get("test_cases", {"mode": "single"})
    if not isinstance(test_cases, dict):
        raise InputAdapterError("adapter.test_cases must be an object")
    _reject_unknown(test_cases, ("mode", "allow_case_deletion"),
                    "adapter.test_cases")
    if test_cases.get("mode", "single") not in ("single", "counted"):
        raise InputAdapterError("adapter.test_cases.mode must be single or counted")
    allow_deletion = test_cases.get("allow_case_deletion", True)
    if type(allow_deletion) is not bool:
        raise InputAdapterError(
            "adapter.test_cases.allow_case_deletion must be boolean"
        )

    spec = schema.get("case")
    if not isinstance(spec, dict):
        raise InputAdapterError("adapter.case must be an object")
    kind = spec.get("kind")
    common = {"kind", "header_fields", "size_field", "index_base"}
    allowed_by_kind = {
        "tree": common | {"node_weights", "edges"},
        "graph": common | {
            "edge_count_field", "edges", "directed", "dag", "connectivity",
            "allow_self_loops", "allow_parallel_edges",
        },
        "operation-sequence": common | {
            "operation_count_field", "initial_array", "interval_ops",
            "right_inclusive", "min_operations", "preserve_prefix_operations",
            "preserve_initial_array",
        },
        "grid": common | {
            "columns_field", "cell_format", "cell_type", "min_rows",
            "min_columns", "replacement_values",
        },
    }
    if kind not in allowed_by_kind:
        raise InputAdapterError(
            "case.kind must be tree, graph, operation-sequence, or grid"
        )
    _reject_unknown(spec, tuple(allowed_by_kind[kind]), "adapter.case")
    fields = _header_fields(spec)
    _field(spec, "size_field", fields)
    _index_base(spec)

    if kind in ("tree", "graph"):
        edge = spec.get("edges")
        if not isinstance(edge, dict):
            raise InputAdapterError("case.edges must be an object")
        _reject_unknown(edge, ("fields", "u_field", "v_field", "weight_field"),
                        "adapter.case.edges")
        _edge_layout(spec)
    if kind == "tree":
        if type(spec.get("node_weights", False)) is not bool:
            raise InputAdapterError("case.node_weights must be boolean")
    elif kind == "graph":
        if _field(spec, "edge_count_field", fields) == spec["size_field"]:
            raise InputAdapterError(
                "case.edge_count_field must differ from size_field"
            )
        for name in ("directed", "dag", "allow_self_loops",
                     "allow_parallel_edges"):
            if type(spec.get(name, False)) is not bool:
                raise InputAdapterError("case.{} must be boolean".format(name))
        if spec.get("connectivity", "none") not in ("none", "weak", "strong"):
            raise InputAdapterError(
                "case.connectivity must be none, weak, or strong"
            )
        if spec.get("dag", False) and not spec.get("directed", False):
            raise InputAdapterError("case.dag=true requires directed=true")
    elif kind == "operation-sequence":
        if _field(spec, "operation_count_field", fields) == spec["size_field"]:
            raise InputAdapterError(
                "case.operation_count_field must differ from size_field"
            )
        if type(spec.get("initial_array", True)) is not bool:
            raise InputAdapterError("case.initial_array must be boolean")
        _string_list(spec.get("interval_ops", []), "case.interval_ops",
                     nonempty=False)
        for name in ("right_inclusive", "preserve_initial_array"):
            if type(spec.get(name, False)) is not bool:
                raise InputAdapterError("case.{} must be boolean".format(name))
        for name in ("min_operations", "preserve_prefix_operations"):
            _positive_int(spec.get(name, 0), "case.{}".format(name),
                          allow_zero=True)
    else:
        if _field(spec, "columns_field", fields) == spec["size_field"]:
            raise InputAdapterError(
                "case.columns_field must differ from size_field"
            )
        if spec.get("cell_format", "tokens") not in ("tokens", "characters"):
            raise InputAdapterError(
                "grid cell_format must be tokens or characters"
            )
        if spec.get("cell_type", "integer") not in ("integer", "symbol"):
            raise InputAdapterError("grid cell_type must be integer or symbol")
        _positive_int(spec.get("min_rows", 1), "grid min_rows")
        _positive_int(spec.get("min_columns", 1), "grid min_columns")
        replacements = _string_list(
            spec.get("replacement_values", []), "grid replacement_values",
            nonempty=False,
        )
        if (spec.get("cell_format", "tokens") == "characters"
                and any(len(item) != 1 for item in replacements)):
            raise InputAdapterError(
                "character-grid replacements must be one character"
            )


def _lines(data: bytes) -> List[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputAdapterError("adapted input must be UTF-8 text: {}".format(exc))
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    if not rows:
        raise InputAdapterError("adapted input is empty")
    return rows


def _int_tokens(line: str, count: int, label: str) -> List[int]:
    tokens = line.split()
    if len(tokens) != count:
        raise InputAdapterError("{} must contain {} integers".format(label, count))
    try:
        return [int(token) for token in tokens]
    except ValueError:
        raise InputAdapterError("{} contains a non-integer token".format(label))


def _parse_header(line: str, spec: Dict[str, Any]) -> Dict[str, int]:
    fields = _header_fields(spec)
    values = _int_tokens(line, len(fields), "case header")
    return dict(zip(fields, values))


def _edge_layout(spec: Dict[str, Any], weighted_default: bool = False) -> Tuple[List[str], str, str, Optional[str]]:
    edge = spec.get("edges", {})
    if not isinstance(edge, dict):
        raise InputAdapterError("case.edges must be an object")
    fields = _string_list(edge.get("fields"), "case.edges.fields")
    u_field = edge.get("u_field", "u")
    v_field = edge.get("v_field", "v")
    if u_field not in fields or v_field not in fields or u_field == v_field:
        raise InputAdapterError("edge endpoint fields are invalid")
    weight_field = edge.get("weight_field")
    if weight_field is None and weighted_default:
        weight_field = "w"
    if weight_field is not None and (
            not isinstance(weight_field, str) or weight_field not in fields
            or weight_field in (u_field, v_field)):
        raise InputAdapterError("edge weight_field is invalid")
    required = {u_field, v_field}
    if weight_field is not None:
        required.add(weight_field)
    if set(fields) != required:
        raise InputAdapterError(
            "edge fields may contain only u/v and the optional weight in any order"
        )
    return fields, u_field, v_field, weight_field


def _parse_edges(lines: Sequence[str], position: int, count: int,
                 spec: Dict[str, Any], n: int) -> Tuple[List[Dict[str, int]], int]:
    fields, u_field, v_field, _ = _edge_layout(spec)
    base = _index_base(spec)
    if position + count > len(lines):
        raise InputAdapterError("input ends before all edge lines")
    result = []
    for offset in range(count):
        values = _int_tokens(lines[position + offset], len(fields), "edge line")
        row = dict(zip(fields, values))
        for endpoint in (row[u_field], row[v_field]):
            if not base <= endpoint < base + n:
                raise InputAdapterError("edge endpoint is outside the declared index range")
        result.append(row)
    return result, position + count


def _parse_case(lines: Sequence[str], position: int,
                spec: Dict[str, Any]) -> Tuple[AdaptedCase, int]:
    if position >= len(lines):
        raise InputAdapterError("input ends before the next test case")
    kind = spec.get("kind")
    if kind not in ("tree", "graph", "operation-sequence", "grid"):
        raise InputAdapterError("case.kind must be tree, graph, operation-sequence, or grid")
    header = _parse_header(lines[position], spec)
    position += 1
    fields = _header_fields(spec)
    size_field = _field(spec, "size_field", fields)
    n = _positive_int(header[size_field], "case size")

    if kind == "tree":
        node_weights_enabled = spec.get("node_weights", False)
        if type(node_weights_enabled) is not bool:
            raise InputAdapterError("case.node_weights must be boolean")
        weights = None
        if node_weights_enabled:
            if position >= len(lines):
                raise InputAdapterError("input ends before tree node weights")
            weights = _int_tokens(lines[position], n, "tree node weights")
            position += 1
        edges, position = _parse_edges(lines, position, n - 1, spec, n)
        return AdaptedCase(kind, header, weights, edges), position

    if kind == "graph":
        edge_count_field = _field(spec, "edge_count_field", fields)
        m = _positive_int(header[edge_count_field], "graph edge count", allow_zero=True)
        edges, position = _parse_edges(lines, position, m, spec, n)
        return AdaptedCase(kind, header, None, edges), position

    if kind == "operation-sequence":
        operation_count_field = _field(spec, "operation_count_field", fields)
        q = _positive_int(header[operation_count_field], "operation count", allow_zero=True)
        initial_enabled = spec.get("initial_array", True)
        if type(initial_enabled) is not bool:
            raise InputAdapterError("case.initial_array must be boolean")
        initial = None
        if initial_enabled:
            if position >= len(lines):
                raise InputAdapterError("input ends before the initial array")
            initial = _int_tokens(lines[position], n, "initial array")
            position += 1
        if position + q > len(lines):
            raise InputAdapterError("input ends before all operation lines")
        operations = [lines[position + offset].split() for offset in range(q)]
        if any(not row for row in operations):
            raise InputAdapterError("operation line is empty")
        interval_ops = set(_string_list(
            spec.get("interval_ops", []), "case.interval_ops", nonempty=False
        ))
        for row in operations:
            if row[0] in interval_ops:
                if len(row) < 3:
                    raise InputAdapterError("interval operation must be op l r [x ...]")
                try:
                    int(row[1])
                    int(row[2])
                except ValueError:
                    raise InputAdapterError("interval endpoints must be integers")
        return AdaptedCase(kind, header, operations=operations, initial=initial), position + q

    # Grid / matrix.
    columns_field = _field(spec, "columns_field", fields)
    columns = _positive_int(header[columns_field], "grid columns")
    if (n < spec.get("min_rows", 1)
            or columns < spec.get("min_columns", 1)):
        raise InputAdapterError("grid dimensions are below configured minima")
    cell_format = spec.get("cell_format", "tokens")
    cell_type = spec.get("cell_type", "integer")
    if cell_format not in ("tokens", "characters"):
        raise InputAdapterError("grid cell_format must be tokens or characters")
    if cell_type not in ("integer", "symbol"):
        raise InputAdapterError("grid cell_type must be integer or symbol")
    if position + n > len(lines):
        raise InputAdapterError("input ends before all grid rows")
    grid: List[List[str]] = []
    for offset in range(n):
        line = lines[position + offset]
        row = line.split() if cell_format == "tokens" else list(line)
        if len(row) != columns:
            raise InputAdapterError("grid row width differs from its header")
        if cell_type == "integer":
            try:
                [int(token) for token in row]
            except ValueError:
                raise InputAdapterError("integer grid contains a non-integer cell")
        grid.append(row)
    return AdaptedCase(kind, header, grid=grid), position + n


def parse_adapted_input(data: bytes, schema: Dict[str, Any]) -> List[AdaptedCase]:
    validate_adapter_schema(schema)
    test_cases = schema.get("test_cases", {"mode": "single"})
    mode = test_cases.get("mode", "single")
    case_spec = schema["case"]
    lines = _lines(data)
    position = 0
    if mode == "counted":
        values = _int_tokens(lines[0], 1, "test count")
        case_count = _positive_int(values[0], "test count")
        position = 1
    else:
        case_count = 1
    cases = []
    for _ in range(case_count):
        case, position = _parse_case(lines, position, case_spec)
        cases.append(case)
    if position != len(lines):
        raise InputAdapterError("adapted input has trailing nonempty lines")
    return cases


def _render_header(header: Dict[str, int], spec: Dict[str, Any]) -> str:
    return " ".join(str(header[field]) for field in _header_fields(spec))


def render_adapted_input(cases: Sequence[AdaptedCase], schema: Dict[str, Any]) -> bytes:
    validate_adapter_schema(schema)
    if not cases:
        raise InputAdapterError("adapted input must retain at least one test case")
    case_spec = schema["case"]
    mode = schema.get("test_cases", {"mode": "single"}).get("mode", "single")
    if mode == "single" and len(cases) != 1:
        raise InputAdapterError("single-case schema cannot render multiple cases")
    lines: List[str] = [str(len(cases))] if mode == "counted" else []
    for case in cases:
        if case.kind != case_spec.get("kind"):
            raise InputAdapterError("case kind differs from adapter schema")
        fields = _header_fields(case_spec)
        size_field = _field(case_spec, "size_field", fields)
        header = dict(case.header)
        if set(header) != set(fields):
            raise InputAdapterError("case header fields differ from adapter schema")
        if case.kind == "grid":
            grid = case.grid or []
            if not grid or not grid[0]:
                raise InputAdapterError("grid must retain at least one row and column")
            if any(len(row) != len(grid[0]) for row in grid):
                raise InputAdapterError("grid rows have inconsistent widths")
            header[size_field] = len(grid)
            columns_field = _field(case_spec, "columns_field", fields)
            header[columns_field] = len(grid[0])
        elif case.kind in ("tree", "graph"):
            if case.kind == "tree":
                header[size_field] = len(case.edges or []) + 1
                if (case.node_weights is not None
                        and len(case.node_weights) != header[size_field]):
                    raise InputAdapterError(
                        "tree node-weight count differs from rendered size"
                    )
            if case.kind == "graph":
                edge_count_field = _field(case_spec, "edge_count_field", fields)
                header[edge_count_field] = len(case.edges or [])
        elif case.kind == "operation-sequence":
            if case.initial is not None and len(case.initial) != header[size_field]:
                raise InputAdapterError(
                    "initial-array length differs from rendered size"
                )
            operation_count_field = _field(case_spec, "operation_count_field", fields)
            header[operation_count_field] = len(case.operations or [])
        lines.append(_render_header(header, case_spec))
        if case.kind == "tree" and case.node_weights is not None:
            lines.append(" ".join(str(value) for value in case.node_weights))
        if case.kind in ("tree", "graph"):
            edge_fields, _, _, _ = _edge_layout(case_spec)
            for edge in case.edges or []:
                lines.append(" ".join(str(edge[field]) for field in edge_fields))
        elif case.kind == "operation-sequence":
            if case.initial is not None:
                lines.append(" ".join(str(value) for value in case.initial))
            lines.extend(" ".join(row) for row in case.operations or [])
        elif case.kind == "grid":
            cell_format = case_spec.get("cell_format", "tokens")
            separator = " " if cell_format == "tokens" else ""
            lines.extend(separator.join(row) for row in case.grid or [])
    return ("\n".join(lines) + "\n").encode("utf-8")


def _canonical(case: AdaptedCase, spec: Dict[str, Any]) -> Tuple[bytes, Dict[str, Any]]:
    fields = _header_fields(spec)
    size_field = _field(spec, "size_field", fields)
    n = case.header[size_field]
    base = _index_base(spec)
    if case.kind in ("tree", "graph"):
        edge_fields, u_field, v_field, weight_field = _edge_layout(spec)
        del edge_fields
        lines = [str(n)] if case.kind == "tree" else ["{} {}".format(n, len(case.edges or []))]
        if case.kind == "tree" and case.node_weights is not None:
            lines.append(" ".join(str(value) for value in case.node_weights))
        for edge in case.edges or []:
            values = [edge[u_field] - base + 1, edge[v_field] - base + 1]
            if weight_field is not None:
                values.append(edge[weight_field])
            lines.append(" ".join(str(value) for value in values))
        domain: Dict[str, Any] = {
            "kind": case.kind,
            "edge_weights": weight_field is not None,
        }
        if case.kind == "tree":
            domain.update({"root": 1, "node_weights": case.node_weights is not None})
        else:
            for name, default in (("directed", False), ("dag", False),
                                  ("connectivity", "none"),
                                  ("allow_self_loops", False),
                                  ("allow_parallel_edges", False)):
                domain[name] = spec.get(name, default)
        return ("\n".join(lines) + "\n").encode("ascii"), domain

    if case.kind == "operation-sequence":
        operations = [list(row) for row in case.operations or []]
        interval_ops = set(spec.get("interval_ops", []))
        for row in operations:
            if row[0] in interval_ops:
                row[1] = str(int(row[1]) - base)
                row[2] = str(int(row[2]) - base)
        lines = ["{} {}".format(n, len(operations))]
        if case.initial is not None:
            lines.append(" ".join(str(value) for value in case.initial))
        lines.extend(" ".join(row) for row in operations)
        domain = {
            "kind": "operation-sequence",
            "initial_array": case.initial is not None,
            "interval_kinds": sorted(interval_ops),
            "index_base": 0,
            "right_inclusive": spec.get("right_inclusive", False),
            "min_operations": spec.get("min_operations", 0),
            "preserve_prefix_operations": spec.get("preserve_prefix_operations", 0),
            "preserve_initial_array": spec.get("preserve_initial_array", False),
        }
        return ("\n".join(lines) + "\n").encode("utf-8"), domain
    raise InputAdapterError("grid cases do not have a V2 canonical representation")


def _from_canonical(data: bytes, template: AdaptedCase,
                    spec: Dict[str, Any]) -> AdaptedCase:
    lines = _lines(data)
    header = dict(template.header)
    fields = _header_fields(spec)
    size_field = _field(spec, "size_field", fields)
    base = _index_base(spec)
    if template.kind in ("tree", "graph"):
        first = _int_tokens(lines[0], 1 if template.kind == "tree" else 2,
                            "canonical header")
        n = first[0]
        m = n - 1 if template.kind == "tree" else first[1]
        position = 1
        weights = None
        if template.kind == "tree" and template.node_weights is not None:
            weights = _int_tokens(lines[position], n, "canonical node weights")
            position += 1
        edge_fields, u_field, v_field, weight_field = _edge_layout(spec)
        width = 3 if weight_field is not None else 2
        edges = []
        for offset in range(m):
            values = _int_tokens(lines[position + offset], width, "canonical edge")
            row = {u_field: values[0] - 1 + base,
                   v_field: values[1] - 1 + base}
            if weight_field is not None:
                row[weight_field] = values[2]
            if set(row) != set(edge_fields):
                raise InputAdapterError("canonical edge cannot be mapped to schema")
            edges.append(row)
        if position + m != len(lines):
            raise InputAdapterError("canonical structural input has trailing lines")
        header[size_field] = n
        if template.kind == "graph":
            edge_count_field = _field(spec, "edge_count_field", fields)
            header[edge_count_field] = m
        return AdaptedCase(template.kind, header, weights, edges)

    first = _int_tokens(lines[0], 2, "canonical operation header")
    n, q = first
    position = 1
    initial = None
    if template.initial is not None:
        initial = _int_tokens(lines[position], n, "canonical initial array")
        position += 1
    if position + q != len(lines):
        raise InputAdapterError("canonical operation count differs from its lines")
    operations = [lines[position + offset].split() for offset in range(q)]
    interval_ops = set(spec.get("interval_ops", []))
    for row in operations:
        if row[0] in interval_ops:
            row[1] = str(int(row[1]) + base)
            row[2] = str(int(row[2]) + base)
    header[size_field] = n
    operation_count_field = _field(spec, "operation_count_field", fields)
    header[operation_count_field] = q
    return AdaptedCase(template.kind, header, operations=operations, initial=initial)


def _smaller_numbers(value: int) -> List[int]:
    half = value // 2 if value >= 0 else -((-value) // 2)
    result = []
    for candidate in (0, 1, -1, half):
        if candidate != value and abs(candidate) <= abs(value) and candidate not in result:
            result.append(candidate)
    return result


def _grid_candidates(case: AdaptedCase, spec: Dict[str, Any]) -> Iterable[Tuple[str, AdaptedCase]]:
    grid = case.grid or []
    rows, columns = len(grid), len(grid[0])
    min_rows = _positive_int(spec.get("min_rows", 1), "grid min_rows")
    min_columns = _positive_int(spec.get("min_columns", 1), "grid min_columns")

    block = int(math.ceil(rows / 2.0))
    while block >= 1:
        if rows - block >= min_rows:
            for start in range(0, rows - block + 1):
                changed = [list(row) for row in grid[:start] + grid[start + block:]]
                yield "grid:delete-rows:{}:{}".format(start, start + block), AdaptedCase(
                    "grid", dict(case.header), grid=changed
                )
        if block == 1:
            break
        block = int(math.ceil(block / 2.0))

    block = int(math.ceil(columns / 2.0))
    while block >= 1:
        if columns - block >= min_columns:
            for start in range(0, columns - block + 1):
                changed = [row[:start] + row[start + block:] for row in grid]
                yield "grid:delete-columns:{}:{}".format(start, start + block), AdaptedCase(
                    "grid", dict(case.header), grid=changed
                )
        if block == 1:
            break
        block = int(math.ceil(block / 2.0))

    if spec.get("cell_type", "integer") == "integer":
        for row_index, row in enumerate(grid):
            for column_index, token in enumerate(row):
                value = int(token)
                for smaller in _smaller_numbers(value):
                    changed = [list(item) for item in grid]
                    changed[row_index][column_index] = str(smaller)
                    yield "grid:shrink-cell:{}:{}:{}->{}".format(
                        row_index, column_index, value, smaller
                    ), AdaptedCase("grid", dict(case.header), grid=changed)
    else:
        replacements = _string_list(
            spec.get("replacement_values", []), "grid replacement_values", nonempty=False
        )
        for row_index, row in enumerate(grid):
            for column_index, token in enumerate(row):
                for replacement in replacements:
                    if replacement == token:
                        continue
                    if spec.get("cell_format", "tokens") == "characters" and len(replacement) != 1:
                        raise InputAdapterError("character-grid replacements must be one character")
                    changed = [list(item) for item in grid]
                    changed[row_index][column_index] = replacement
                    yield "grid:replace-cell:{}:{}:{}->{}".format(
                        row_index, column_index, token, replacement
                    ), AdaptedCase("grid", dict(case.header), grid=changed)


def _delete_cases(cases: List[AdaptedCase], schema: Dict[str, Any], attempt: Attempt,
                  can_attempt: CanAttempt) -> Tuple[List[AdaptedCase], List[str]]:
    current = list(cases)
    accepted: List[str] = []
    block = int(math.ceil(len(current) / 2.0))
    while len(current) > 1 and can_attempt():
        changed = False
        while block >= 1 and not changed:
            for start in range(0, len(current) - block + 1):
                trial = current[:start] + current[start + block:]
                if not trial:
                    continue
                label = "adapter:delete-cases:{}:{}".format(start, start + block)
                if attempt(render_adapted_input(trial, schema), label):
                    current = trial
                    accepted.append(label)
                    block = int(math.ceil(len(current) / 2.0))
                    changed = True
                    break
                if not can_attempt():
                    break
            if block == 1 or not can_attempt():
                break
            block = int(math.ceil(block / 2.0))
        if not changed:
            break
    return current, accepted


def shrink_adapted_input(data: bytes, schema: Dict[str, Any], attempt: Attempt,
                         can_attempt: CanAttempt) -> Tuple[bytes, Dict[str, Any]]:
    """Shrink a declared OI input while delegating every acceptance to ``attempt``."""
    cases = parse_adapted_input(data, schema)
    original_count = len(cases)
    case_spec = schema["case"]
    mode = schema.get("test_cases", {"mode": "single"}).get("mode", "single")
    delete_enabled = schema.get("test_cases", {}).get("allow_case_deletion", True)
    if type(delete_enabled) is not bool:
        raise InputAdapterError("adapter.test_cases.allow_case_deletion must be boolean")
    accepted_case_deletions: List[str] = []
    if mode == "counted" and delete_enabled:
        cases, accepted_case_deletions = _delete_cases(
            cases, schema, attempt, can_attempt
        )

    reports = []
    for case_index in range(len(cases)):
        if not can_attempt():
            break
        template = cases[case_index]
        if template.kind == "grid":
            current = template
            accepted = []
            seen = {hashlib.sha256(render_adapted_input([current], {
                "schema_version": 1, "test_cases": {"mode": "single"},
                "case": case_spec,
            })).hexdigest()}
            rounds = 0
            while can_attempt():
                rounds += 1
                changed = False
                for label, candidate in _grid_candidates(current, case_spec):
                    single_schema = {"schema_version": 1,
                                     "test_cases": {"mode": "single"},
                                     "case": case_spec}
                    digest = hashlib.sha256(render_adapted_input([candidate], single_schema)).hexdigest()
                    if digest in seen:
                        continue
                    seen.add(digest)
                    trial_cases = list(cases)
                    trial_cases[case_index] = candidate
                    full_label = "adapter:case:{}:{}".format(case_index, label)
                    if attempt(render_adapted_input(trial_cases, schema), full_label):
                        current = candidate
                        accepted.append(label)
                        changed = True
                        break
                    if not can_attempt():
                        break
                if not changed:
                    break
            cases[case_index] = current
            reports.append({"index": case_index, "kind": "grid", "rounds": rounds,
                            "accepted_transforms": accepted,
                            "rows": len(current.grid or []),
                            "columns": len((current.grid or [[]])[0])})
            continue

        canonical, domain = _canonical(template, case_spec)

        def adapted_attempt(candidate: bytes, label: str) -> bool:
            mapped = _from_canonical(candidate, template, case_spec)
            trial_cases = list(cases)
            trial_cases[case_index] = mapped
            return attempt(
                render_adapted_input(trial_cases, schema),
                "adapter:case:{}:{}".format(case_index, label),
            )

        try:
            minimized, domain_report = shrink_domain(
                canonical, domain, adapted_attempt, can_attempt
            )
        except DomainShrinkError as exc:
            raise InputAdapterError("adapted {} case: {}".format(template.kind, exc))
        cases[case_index] = _from_canonical(minimized, template, case_spec)
        reports.append(dict(domain_report, index=case_index))

    rendered = render_adapted_input(cases, schema)
    # Parse our own output before the external validator sees it, so malformed
    # adapter rendering fails closed rather than being treated as a proposal.
    parse_adapted_input(rendered, schema)
    return rendered, {
        "schema_version": 1,
        "mode": mode,
        "kind": case_spec.get("kind"),
        "original_cases": original_count,
        "minimized_cases": len(cases),
        "accepted_case_deletions": accepted_case_deletions,
        "case_reports": reports,
    }


def inspect_adapted_input(data: bytes, schema: Dict[str, Any]) -> Dict[str, Any]:
    cases = parse_adapted_input(data, schema)
    summaries = []
    spec = schema["case"]
    fields = _header_fields(spec)
    size_field = _field(spec, "size_field", fields)
    for index, case in enumerate(cases):
        row: Dict[str, Any] = {"index": index, "kind": case.kind,
                               "size": case.header[size_field]}
        if case.kind in ("tree", "graph"):
            row["edges"] = len(case.edges or [])
        elif case.kind == "operation-sequence":
            row["operations"] = len(case.operations or [])
        else:
            row["rows"] = len(case.grid or [])
            row["columns"] = len((case.grid or [[]])[0])
        summaries.append(row)
    rendered = render_adapted_input(cases, schema)
    return {
        "schema_version": 1,
        "valid": True,
        "cases": len(cases),
        "case_summaries": summaries,
        "normalized_bytes": len(rendered),
        "normalized_sha256": hashlib.sha256(rendered).hexdigest(),
    }
