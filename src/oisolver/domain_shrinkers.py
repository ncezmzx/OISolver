"""Validator-guarded structural shrink candidates for common OI input domains.

The codecs are intentionally explicit rather than guessing arbitrary contest
formats.  A differential-test config selects one canonical codec; every
candidate is still accepted only by differential.py after the problem's own
validator and candidate/oracle mismatch both succeed.
"""
from dataclasses import dataclass
import hashlib
import math
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


class DomainShrinkError(ValueError):
    pass


Attempt = Callable[[bytes, str], bool]
CanAttempt = Callable[[], bool]


def _int(token: bytes, label: str) -> int:
    try:
        return int(token)
    except ValueError:
        raise DomainShrinkError("{} must be an integer".format(label))


def _smaller_numbers(value: int) -> List[int]:
    choices: List[int] = []
    half_toward_zero = value // 2 if value >= 0 else -((-value) // 2)
    for candidate in (0, 1, -1, half_toward_zero):
        if candidate != value and abs(candidate) <= abs(value) and candidate not in choices:
            choices.append(candidate)
    return choices


def _lines(data: bytes) -> List[List[bytes]]:
    rows = [line.split() for line in data.splitlines() if line.strip()]
    if not rows:
        raise DomainShrinkError("Structured input is empty")
    return rows


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class _Tree:
    n: int
    node_weights: Optional[Tuple[int, ...]]
    edges: Tuple[Tuple[int, int, Optional[int]], ...]


def _parse_tree(data: bytes, spec: Dict[str, Any]) -> _Tree:
    rows = _lines(data)
    if len(rows[0]) != 1:
        raise DomainShrinkError("tree first line must contain n")
    n = _int(rows[0][0], "tree.n")
    if n <= 0:
        raise DomainShrinkError("tree.n must be positive")
    weighted_nodes = spec.get("node_weights", False)
    weighted_edges = spec.get("edge_weights", False)
    if type(weighted_nodes) is not bool or type(weighted_edges) is not bool:
        raise DomainShrinkError("tree node_weights/edge_weights must be boolean")
    position = 1
    node_weights: Optional[Tuple[int, ...]] = None
    if weighted_nodes:
        if position >= len(rows) or len(rows[position]) != n:
            raise DomainShrinkError("tree node-weight line must contain n integers")
        node_weights = tuple(_int(token, "tree node weight") for token in rows[position])
        position += 1
    edge_rows = rows[position:]
    if len(edge_rows) != n - 1:
        raise DomainShrinkError("tree must contain exactly n-1 edge lines")
    width = 3 if weighted_edges else 2
    edges: List[Tuple[int, int, Optional[int]]] = []
    adjacency = [[] for _ in range(n + 1)]
    for row in edge_rows:
        if len(row) != width:
            raise DomainShrinkError("tree edge width does not match edge_weights")
        u, v = _int(row[0], "tree edge.u"), _int(row[1], "tree edge.v")
        if not (1 <= u <= n and 1 <= v <= n) or u == v:
            raise DomainShrinkError("tree edge endpoint is invalid")
        weight = _int(row[2], "tree edge.weight") if weighted_edges else None
        edges.append((u, v, weight))
        adjacency[u].append(v)
        adjacency[v].append(u)
    seen = {1}
    stack = [1]
    while stack:
        node = stack.pop()
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    if len(seen) != n:
        raise DomainShrinkError("tree is disconnected")
    return _Tree(n, node_weights, tuple(edges))


def _encode_tree(tree: _Tree) -> bytes:
    rows = [str(tree.n)]
    if tree.node_weights is not None:
        rows.append(" ".join(str(value) for value in tree.node_weights))
    for u, v, weight in tree.edges:
        row = "{} {}".format(u, v)
        if weight is not None:
            row += " {}".format(weight)
        rows.append(row)
    return ("\n".join(rows) + "\n").encode("ascii")


def _tree_adjacency(tree: _Tree) -> List[List[Tuple[int, int, Optional[int]]]]:
    adjacency: List[List[Tuple[int, int, Optional[int]]]] = [[] for _ in range(tree.n + 1)]
    for index, (u, v, weight) in enumerate(tree.edges):
        adjacency[u].append((v, index, weight))
        adjacency[v].append((u, index, weight))
    return adjacency


def _tree_remove_vertex(tree: _Tree, removed: int,
                        replacement_edges: Sequence[Tuple[int, int, Optional[int]]]) -> _Tree:
    mapping: Dict[int, int] = {}
    next_id = 1
    for vertex in range(1, tree.n + 1):
        if vertex != removed:
            mapping[vertex] = next_id
            next_id += 1
    kept = [edge for edge in tree.edges if removed not in edge[:2]]
    kept.extend(replacement_edges)
    edges = tuple((mapping[u], mapping[v], weight) for u, v, weight in kept)
    weights = None
    if tree.node_weights is not None:
        weights = tuple(value for index, value in enumerate(tree.node_weights, 1)
                        if index != removed)
    return _Tree(tree.n - 1, weights, edges)


def _tree_candidates(data: bytes, spec: Dict[str, Any]) -> Iterable[Tuple[str, bytes]]:
    root = spec.get("root", 1)
    if type(root) is not int or root != 1:
        raise DomainShrinkError("built-in tree shrinker currently requires integer root=1")
    tree = _parse_tree(data, spec)
    adjacency = _tree_adjacency(tree)

    if tree.n > 1:
        for vertex in range(2, tree.n + 1):
            if len(adjacency[vertex]) == 1:
                reduced = _tree_remove_vertex(tree, vertex, [])
                yield "tree:delete-leaf:{}".format(vertex), _encode_tree(reduced)

        parent = [0] * (tree.n + 1)
        parent_edge: List[Optional[int]] = [None] * (tree.n + 1)
        order = [1]
        for node in order:
            for neighbor, edge_index, _ in adjacency[node]:
                if neighbor != parent[node]:
                    parent[neighbor] = node
                    parent_edge[neighbor] = edge_index
                    order.append(neighbor)
        for vertex in range(2, tree.n + 1):
            children = [item for item in adjacency[vertex] if item[0] != parent[vertex]]
            if not children:
                continue
            replacement = [(parent[vertex], child, weight)
                           for child, _, weight in children]
            reduced = _tree_remove_vertex(tree, vertex, replacement)
            yield "tree:contract-subtree-root:{}".format(vertex), _encode_tree(reduced)

    if tree.node_weights is not None:
        for index, value in enumerate(tree.node_weights):
            for smaller in _smaller_numbers(value):
                weights = list(tree.node_weights)
                weights[index] = smaller
                reduced = _Tree(tree.n, tuple(weights), tree.edges)
                yield "tree:shrink-node-weight:{}:{}->{}".format(
                    index + 1, value, smaller), _encode_tree(reduced)
    for index, (u, v, weight) in enumerate(tree.edges):
        if weight is None:
            continue
        for smaller in _smaller_numbers(weight):
            edges = list(tree.edges)
            edges[index] = (u, v, smaller)
            reduced = _Tree(tree.n, tree.node_weights, tuple(edges))
            yield "tree:shrink-edge-weight:{}:{}->{}".format(
                index, weight, smaller), _encode_tree(reduced)


@dataclass(frozen=True)
class _Graph:
    n: int
    edges: Tuple[Tuple[int, int, Optional[int]], ...]


def _parse_graph(data: bytes, spec: Dict[str, Any]) -> _Graph:
    rows = _lines(data)
    if len(rows[0]) != 2:
        raise DomainShrinkError("graph first line must contain n m")
    n, m = _int(rows[0][0], "graph.n"), _int(rows[0][1], "graph.m")
    if n <= 0 or m < 0 or len(rows) != m + 1:
        raise DomainShrinkError("graph dimensions do not match edge lines")
    weighted = spec.get("edge_weights", False)
    if type(weighted) is not bool:
        raise DomainShrinkError("graph.edge_weights must be boolean")
    width = 3 if weighted else 2
    edges: List[Tuple[int, int, Optional[int]]] = []
    for row in rows[1:]:
        if len(row) != width:
            raise DomainShrinkError("graph edge width does not match edge_weights")
        u, v = _int(row[0], "graph edge.u"), _int(row[1], "graph edge.v")
        if not (1 <= u <= n and 1 <= v <= n):
            raise DomainShrinkError("graph edge endpoint is invalid")
        weight = _int(row[2], "graph edge.weight") if weighted else None
        edges.append((u, v, weight))
    graph = _Graph(n, tuple(edges))
    if not _graph_constraints_hold(graph, spec):
        raise DomainShrinkError("initial graph violates configured structural constraints")
    return graph


def _encode_graph(graph: _Graph) -> bytes:
    rows = ["{} {}".format(graph.n, len(graph.edges))]
    for u, v, weight in graph.edges:
        row = "{} {}".format(u, v)
        if weight is not None:
            row += " {}".format(weight)
        rows.append(row)
    return ("\n".join(rows) + "\n").encode("ascii")


def _reachable(n: int, edges: Sequence[Tuple[int, int, Optional[int]]],
               directed: bool, reverse: bool = False) -> int:
    adjacency = [[] for _ in range(n + 1)]
    for u, v, _ in edges:
        if reverse:
            u, v = v, u
        adjacency[u].append(v)
        if not directed:
            adjacency[v].append(u)
    seen = {1}
    stack = [1]
    while stack:
        node = stack.pop()
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return len(seen)


def _is_dag(graph: _Graph) -> bool:
    indegree = [0] * (graph.n + 1)
    adjacency = [[] for _ in range(graph.n + 1)]
    for u, v, _ in graph.edges:
        adjacency[u].append(v)
        indegree[v] += 1
    queue = [vertex for vertex in range(1, graph.n + 1) if indegree[vertex] == 0]
    visited = 0
    for vertex in queue:
        visited += 1
        for neighbor in adjacency[vertex]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    return visited == graph.n


def _graph_constraints_hold(graph: _Graph, spec: Dict[str, Any]) -> bool:
    directed = spec.get("directed", False)
    if type(directed) is not bool:
        raise DomainShrinkError("graph.directed must be boolean")
    allow_self = spec.get("allow_self_loops", False)
    allow_parallel = spec.get("allow_parallel_edges", False)
    if type(allow_self) is not bool or type(allow_parallel) is not bool:
        raise DomainShrinkError("graph loop/parallel flags must be boolean")
    seen = set()
    for u, v, _ in graph.edges:
        if not allow_self and u == v:
            return False
        identity = (u, v) if directed else tuple(sorted((u, v)))
        if not allow_parallel and identity in seen:
            return False
        seen.add(identity)
    dag = spec.get("dag", False)
    if type(dag) is not bool:
        raise DomainShrinkError("graph.dag must be boolean")
    if dag and (not directed or not _is_dag(graph)):
        return False
    connectivity = spec.get("connectivity", "none")
    if connectivity not in ("none", "weak", "strong"):
        raise DomainShrinkError("graph.connectivity must be none, weak, or strong")
    if connectivity == "weak":
        undirected_edges = tuple((u, v, weight) for u, v, weight in graph.edges)
        if _reachable(graph.n, undirected_edges, False) != graph.n:
            return False
    elif connectivity == "strong":
        if not directed:
            return _reachable(graph.n, graph.edges, False) == graph.n
        if (_reachable(graph.n, graph.edges, True) != graph.n
                or _reachable(graph.n, graph.edges, True, reverse=True) != graph.n):
            return False
    return True


def _drop_graph_vertices(graph: _Graph, removed: Sequence[int]) -> _Graph:
    removed_set = set(removed)
    mapping: Dict[int, int] = {}
    next_id = 1
    for vertex in range(1, graph.n + 1):
        if vertex not in removed_set:
            mapping[vertex] = next_id
            next_id += 1
    edges = tuple((mapping[u], mapping[v], weight) for u, v, weight in graph.edges
                  if u not in removed_set and v not in removed_set)
    return _Graph(graph.n - len(removed_set), edges)


def _isolated_vertices(graph: _Graph) -> List[int]:
    degree = [0] * (graph.n + 1)
    for u, v, _ in graph.edges:
        degree[u] += 1
        degree[v] += 1
    return [vertex for vertex in range(1, graph.n + 1) if degree[vertex] == 0]


def _graph_candidates(data: bytes, spec: Dict[str, Any]) -> Iterable[Tuple[str, bytes]]:
    graph = _parse_graph(data, spec)
    for index in range(len(graph.edges)):
        edges = graph.edges[:index] + graph.edges[index + 1:]
        reduced = _Graph(graph.n, edges)
        if _graph_constraints_hold(reduced, spec):
            yield "graph:delete-edge:{}".format(index), _encode_graph(reduced)
        isolated = _isolated_vertices(reduced)
        if isolated and len(isolated) < reduced.n:
            compact = _drop_graph_vertices(reduced, isolated)
            if _graph_constraints_hold(compact, spec):
                yield "graph:delete-edge-and-isolated:{}:{}".format(
                    index, ",".join(str(v) for v in isolated)), _encode_graph(compact)

    isolated = _isolated_vertices(graph)
    for vertex in isolated:
        if graph.n <= 1:
            break
        reduced = _drop_graph_vertices(graph, [vertex])
        if _graph_constraints_hold(reduced, spec):
            yield "graph:delete-isolated-and-renumber:{}".format(vertex), _encode_graph(reduced)

    for index, (u, v, weight) in enumerate(graph.edges):
        if weight is None:
            continue
        for smaller in _smaller_numbers(weight):
            edges = list(graph.edges)
            edges[index] = (u, v, smaller)
            reduced = _Graph(graph.n, tuple(edges))
            if _graph_constraints_hold(reduced, spec):
                yield "graph:shrink-edge-weight:{}:{}->{}".format(
                    index, weight, smaller), _encode_graph(reduced)


@dataclass(frozen=True)
class _Operations:
    n: int
    initial: Optional[Tuple[int, ...]]
    operations: Tuple[Tuple[bytes, ...], ...]


def _parse_operations(data: bytes, spec: Dict[str, Any]) -> _Operations:
    rows = _lines(data)
    if len(rows[0]) != 2:
        raise DomainShrinkError("operation sequence first line must contain n q")
    n, q = _int(rows[0][0], "operations.n"), _int(rows[0][1], "operations.q")
    if n <= 0 or q < 0:
        raise DomainShrinkError("operation sequence dimensions are invalid")
    initial_array = spec.get("initial_array", True)
    if type(initial_array) is not bool:
        raise DomainShrinkError("operation-sequence.initial_array must be boolean")
    position = 1
    initial: Optional[Tuple[int, ...]] = None
    if initial_array:
        if position >= len(rows) or len(rows[position]) != n:
            raise DomainShrinkError("operation initial array must contain n integers")
        initial = tuple(_int(token, "initial value") for token in rows[position])
        position += 1
    operations = tuple(tuple(row) for row in rows[position:])
    if len(operations) != q:
        raise DomainShrinkError("operation q does not match operation lines")
    return _Operations(n, initial, operations)


def _encode_operations(value: _Operations) -> bytes:
    rows = ["{} {}".format(value.n, len(value.operations))]
    if value.initial is not None:
        rows.append(" ".join(str(item) for item in value.initial))
    rows.extend(" ".join(token.decode("ascii") for token in row)
                for row in value.operations)
    return ("\n".join(rows) + "\n").encode("ascii")


def _replace_token(row: Tuple[bytes, ...], index: int, value: int) -> Tuple[bytes, ...]:
    changed = list(row)
    changed[index] = str(value).encode("ascii")
    return tuple(changed)


def _operation_candidates(data: bytes, spec: Dict[str, Any]) -> Iterable[Tuple[str, bytes]]:
    value = _parse_operations(data, spec)
    operations = value.operations
    minimum = spec.get("min_operations", 0)
    if type(minimum) is not int or minimum < 0:
        raise DomainShrinkError("operation-sequence.min_operations must be nonnegative")
    preserved_prefix = spec.get("preserve_prefix_operations", 0)
    if (type(preserved_prefix) is not int or preserved_prefix < 0
            or preserved_prefix > len(operations)):
        raise DomainShrinkError(
            "operation-sequence.preserve_prefix_operations is invalid"
        )
    preserve_initial = spec.get("preserve_initial_array", False)
    if type(preserve_initial) is not bool:
        raise DomainShrinkError("operation-sequence.preserve_initial_array must be boolean")
    minimum = max(minimum, preserved_prefix)

    length = len(operations)
    block = int(math.ceil(length / 2.0)) if length else 0
    emitted_blocks = set()
    while block >= 2:
        for start in range(preserved_prefix, length - block + 1):
            if length - block < minimum or (start, block) in emitted_blocks:
                continue
            emitted_blocks.add((start, block))
            reduced = _Operations(value.n, value.initial,
                                  operations[:start] + operations[start + block:])
            yield "operations:delete-block:{}:{}".format(start, start + block), _encode_operations(reduced)
        if block == 2:
            break
        block = int(math.ceil(block / 2.0))
    for index in range(preserved_prefix, length):
        if length - 1 < minimum:
            break
        reduced = _Operations(value.n, value.initial,
                              operations[:index] + operations[index + 1:])
        yield "operations:delete-one:{}".format(index), _encode_operations(reduced)

    interval_kinds = spec.get("interval_kinds", ["add", "set", "query"])
    if not isinstance(interval_kinds, list) or any(not isinstance(item, str)
                                                   for item in interval_kinds):
        raise DomainShrinkError("operation-sequence.interval_kinds must be strings")
    index_base = spec.get("index_base", 0)
    right_inclusive = spec.get("right_inclusive", False)
    if type(index_base) is not int or type(right_inclusive) is not bool:
        raise DomainShrinkError("operation sequence index settings are invalid")
    interval_set = {item.encode("ascii") for item in interval_kinds}

    for op_index, row in enumerate(operations):
        if op_index < preserved_prefix:
            continue
        if row and row[0] in interval_set and len(row) >= 3:
            left = _int(row[1], "operation.left")
            right = _int(row[2], "operation.right")
            minimum_width = 0 if right_inclusive else 1
            endpoint_choices = []
            new_right = left + minimum_width
            if new_right != right:
                endpoint_choices.append((2, new_right, "right"))
            new_left = right - minimum_width
            if new_left != left:
                endpoint_choices.append((1, new_left, "left"))
            middle = (left + right) // 2
            if left < middle < right:
                endpoint_choices.extend([(2, middle, "right-mid"),
                                         (1, middle, "left-mid")])
            for token_index, endpoint, name in endpoint_choices:
                changed_row = _replace_token(row, token_index, endpoint)
                changed_ops = list(operations)
                changed_ops[op_index] = changed_row
                reduced = _Operations(value.n, value.initial, tuple(changed_ops))
                yield "operations:shrink-interval:{}:{}:{}".format(
                    op_index, name, endpoint), _encode_operations(reduced)

        start = 3 if row and row[0] in interval_set else 1
        for token_index in range(start, len(row)):
            try:
                number = int(row[token_index])
            except ValueError:
                continue
            for smaller in _smaller_numbers(number):
                changed_row = _replace_token(row, token_index, smaller)
                changed_ops = list(operations)
                changed_ops[op_index] = changed_row
                reduced = _Operations(value.n, value.initial, tuple(changed_ops))
                yield "operations:shrink-parameter:{}:{}:{}->{}".format(
                    op_index, token_index, number, smaller), _encode_operations(reduced)

    if value.initial is not None and not preserve_initial:
        for index, number in enumerate(value.initial):
            for smaller in _smaller_numbers(number):
                initial = list(value.initial)
                initial[index] = smaller
                reduced = _Operations(value.n, tuple(initial), operations)
                yield "operations:shrink-initial:{}:{}->{}".format(
                    index, number, smaller), _encode_operations(reduced)


def _summary(data: bytes, spec: Dict[str, Any]) -> Dict[str, int]:
    kind = spec.get("kind")
    if kind == "tree":
        value = _parse_tree(data, spec)
        return {"vertices": value.n, "edges": len(value.edges)}
    if kind == "graph":
        value = _parse_graph(data, spec)
        return {"vertices": value.n, "edges": len(value.edges)}
    if kind == "operation-sequence":
        value = _parse_operations(data, spec)
        return {"array_size": value.n, "operations": len(value.operations)}
    raise DomainShrinkError("Unknown domain shrinker kind: {}".format(kind))


def _candidates(data: bytes, spec: Dict[str, Any]) -> Iterable[Tuple[str, bytes]]:
    kind = spec.get("kind")
    if kind == "tree":
        return _tree_candidates(data, spec)
    if kind == "graph":
        return _graph_candidates(data, spec)
    if kind == "operation-sequence":
        return _operation_candidates(data, spec)
    raise DomainShrinkError("Unknown domain shrinker kind: {}".format(kind))


def shrink_domain(data: bytes, spec: Dict[str, Any], attempt: Attempt,
                  can_attempt: CanAttempt) -> Tuple[bytes, Dict[str, Any]]:
    """Greedily accept structural candidates through the caller's guarded probe.

    ``attempt`` must perform both legality validation and mismatch reproduction.
    This module never accepts a candidate on shape checks alone.
    """
    if not isinstance(spec, dict):
        raise DomainShrinkError("shrink.domain must be an object")
    kind = spec.get("kind")
    if kind not in ("tree", "graph", "operation-sequence"):
        raise DomainShrinkError("shrink.domain.kind must be tree, graph, or operation-sequence")
    original_summary = _summary(data, spec)
    current = data
    accepted: List[str] = []
    seen = {_digest(data)}
    rounds = 0
    while can_attempt():
        rounds += 1
        changed = False
        for label, candidate in _candidates(current, spec):
            digest = _digest(candidate)
            if digest in seen:
                continue
            seen.add(digest)
            if not can_attempt():
                break
            if attempt(candidate, label):
                current = candidate
                accepted.append(label)
                changed = True
                break
        if not changed:
            break
    return current, {
        "kind": kind,
        "codec": "oisolver-canonical-v1",
        "rounds": rounds,
        "accepted_transforms": accepted,
        "original": original_summary,
        "minimized": _summary(current, spec),
    }
