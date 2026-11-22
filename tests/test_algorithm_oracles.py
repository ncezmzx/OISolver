"""Small independent OI oracles; finite checks are not universal proof certificates."""
from itertools import product
import heapq
import unittest


def cdq_strict_count(points):
    groups = []
    for x, y in sorted(points):
        if not groups or groups[-1][0] != x:
            groups.append((x, []))
        groups[-1][1].append(y)

    def solve(left, right):
        if right - left == 1:
            return 0, sorted(groups[left][1])
        middle = (left + right) // 2
        a, ys_left = solve(left, middle)
        b, ys_right = solve(middle, right)
        cursor = cross = 0
        for y in ys_right:
            while cursor < len(ys_left) and ys_left[cursor] <= y:
                cursor += 1
            cross += cursor
        return a + b + cross, sorted(ys_left + ys_right)

    return solve(0, len(groups))[0] if groups else 0


def exclusions_prefix_suffix(values, operation, identity):
    prefix = [identity]
    for value in values:
        prefix.append(operation(prefix[-1], value))
    suffix = [identity] * (len(values) + 1)
    for i in range(len(values) - 1, -1, -1):
        suffix[i] = operation(values[i], suffix[i + 1])
    return [operation(prefix[i], suffix[i + 1]) for i in range(len(values))]


def apply_tag(tag, value):
    assignment, addition = tag
    if assignment is not None:
        value = assignment
    return value + addition


def compose(new, old):
    """Return the function new(old(x))."""
    new_assignment, new_addition = new
    old_assignment, old_addition = old
    if new_assignment is not None:
        return new_assignment, new_addition
    if old_assignment is not None:
        return old_assignment, old_addition + new_addition
    return None, old_addition + new_addition


def build(left, right, counter):
    counter[0] += 1
    if right - left == 1:
        return (0, None, None)
    middle = (left + right) // 2
    return (0, build(left, middle, counter), build(middle, right, counter))


def persistent_update(node, left, right, position, value, counter):
    counter[0] += 1
    if right - left == 1:
        return (value, None, None)
    middle = (left + right) // 2
    total, a, b = node
    if position < middle:
        a = persistent_update(a, left, middle, position, value, counter)
    else:
        b = persistent_update(b, middle, right, position, value, counter)
    return (a[0] + b[0], a, b)


def persistent_query(node, left, right, position):
    if right - left == 1:
        return node[0]
    middle = (left + right) // 2
    return (persistent_query(node[1], left, middle, position) if position < middle
            else persistent_query(node[2], middle, right, position))


class AlgorithmOracles(unittest.TestCase):
    def test_cdq_strict_ties(self):
        domain = list(product(range(2), repeat=2))
        for n in range(5):
            for points in product(domain, repeat=n):
                expected = sum(x < xx and y <= yy
                               for i, (x, y) in enumerate(points)
                               for j, (xx, yy) in enumerate(points) if i != j)
                self.assertEqual(cdq_strict_count(points), expected, points)
        # Splitting equal x without grouping would incorrectly count this pair.
        self.assertEqual(cdq_strict_count([(0, 0), (0, 1)]), 0)

    def test_per_node_sorting_sum(self):
        for exponent in range(1, 15):
            n = 1 << exponent
            measured = sum((1 << depth) * (n >> depth) * (exponent - depth)
                           for depth in range(exponent))
            expected = n * exponent * (exponent + 1) // 2
            self.assertEqual(measured, expected)
            self.assertGreaterEqual(measured, n * exponent)

    def test_prefix_suffix_exclusion(self):
        operation = lambda a, b: (a * b) % 7
        for length in range(1, 7):
            for values in product(range(4), repeat=length):
                expected = []
                for excluded in range(length):
                    result = 1
                    for i, value in enumerate(values):
                        if i != excluded:
                            result = operation(result, value)
                    expected.append(result)
                self.assertEqual(exclusions_prefix_suffix(values, operation, 1), expected)

    def test_lazy_tag_composition(self):
        tags = [(None, amount) for amount in range(-2, 3)]
        tags += [(value, amount) for value in range(-2, 3) for amount in range(-1, 2)]
        for old in tags:
            for new in tags:
                merged = compose(new, old)
                for value in range(-3, 4):
                    self.assertEqual(apply_tag(merged, value),
                                     apply_tag(new, apply_tag(old, value)))
        self.assertNotEqual(compose((4, 0), (None, 2)), compose((None, 2), (4, 0)))

    def test_persistent_path_copy(self):
        n = 8
        counter = [0]
        root = build(0, n, counter)
        roots = [root]
        arrays = [[0] * n]
        updates = [(3, 7), (5, 2), (3, -1), (0, 9)]
        previous_nodes = counter[0]
        for position, value in updates:
            roots.append(persistent_update(roots[-1], 0, n, position, value, counter))
            expected = arrays[-1][:]
            expected[position] = value
            arrays.append(expected)
            self.assertLessEqual(counter[0] - previous_nodes, 4)  # root plus log2(8) descendants
            previous_nodes = counter[0]
            for version, version_root in enumerate(roots):
                actual = [persistent_query(version_root, 0, n, i) for i in range(n)]
                self.assertEqual(actual, arrays[version])

    def test_dynamic_segment_tree_node_bound(self):
        depth = 6
        values = range(1 << depth)
        for length in range(5):
            for sequence in product(range(8), repeat=length):
                allocated = {("sentinel", 0)}
                for value in sequence:
                    for level in range(depth + 1):
                        allocated.add((level, value >> (depth - level)))
                self.assertLessEqual(len(allocated), 1 + length * (depth + 1))

    def test_heap_dijkstra_is_valid_for_zero_one_weights(self):
        def heap_shortest(graph):
            distance = [10 ** 9] * len(graph)
            distance[0] = 0
            queue = [(0, 0)]
            while queue:
                current, u = heapq.heappop(queue)
                if current != distance[u]:
                    continue
                for v, weight in graph[u]:
                    candidate = current + weight
                    if candidate < distance[v]:
                        distance[v] = candidate
                        heapq.heappush(queue, (candidate, v))
            return distance

        for edge_states in product(range(3), repeat=6):
            # Four vertices, six forward edges; state 0 absent, 1/2 encode weights 0/1.
            graph = [[] for _ in range(4)]
            index = 0
            for u in range(4):
                for v in range(u + 1, 4):
                    state = edge_states[index]
                    index += 1
                    if state:
                        graph[u].append((v, state - 1))
            expected = [10 ** 9] * 4
            expected[0] = 0
            for u in range(4):
                for v, weight in graph[u]:
                    expected[v] = min(expected[v], expected[u] + weight)
            self.assertEqual(heap_shortest(graph), expected)


if __name__ == "__main__":
    unittest.main()
