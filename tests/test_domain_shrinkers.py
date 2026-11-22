import unittest

from oisolver.domain_shrinkers import DomainShrinkError, shrink_domain


class DomainShrinkers(unittest.TestCase):
    def test_tree_subtree_contraction_and_weight_candidates(self):
        data = b"4\n9 8 7 6\n1 2 5\n2 3 4\n2 4 3\n"
        seen = []

        def attempt(candidate, label):
            seen.append(label)
            return label.startswith("tree:contract-subtree-root:2")

        minimized, report = shrink_domain(
            data,
            {"kind": "tree", "root": 1, "node_weights": True,
             "edge_weights": True},
            attempt,
            lambda: len(seen) < 30,
        )
        self.assertIn("tree:contract-subtree-root:2", report["accepted_transforms"])
        self.assertEqual(report["minimized"], {"vertices": 3, "edges": 2})
        self.assertTrue(any(label.startswith("tree:delete-leaf") for label in seen))
        self.assertTrue(any(label.startswith("tree:shrink-node-weight") for label in seen))
        self.assertTrue(any(label.startswith("tree:shrink-edge-weight") for label in seen))
        self.assertEqual(minimized.splitlines()[0], b"3")

    def test_graph_deletion_isolated_reindex_and_weight_shrink(self):
        data = b"4 3\n1 2 9\n2 3 5\n1 3 4\n"
        seen = []
        isolated_done = [False]
        edge_done = [False]

        def attempt(candidate, label):
            seen.append(label)
            if label.startswith("graph:delete-edge-and-isolated") and not isolated_done[0]:
                isolated_done[0] = True
                edge_done[0] = True
                return True
            if edge_done[0] and label.startswith("graph:shrink-edge-weight"):
                return True
            return False

        minimized, report = shrink_domain(
            data,
            {"kind": "graph", "directed": False, "edge_weights": True,
             "connectivity": "none", "allow_self_loops": False,
             "allow_parallel_edges": False},
            attempt,
            lambda: len(seen) < 80,
        )
        self.assertTrue(isolated_done[0])
        self.assertTrue(edge_done[0])
        self.assertEqual(report["minimized"]["vertices"], 3)
        self.assertEqual(report["minimized"]["edges"], 2)
        self.assertTrue(any(label.startswith("graph:shrink-edge-weight")
                            for label in report["accepted_transforms"]))
        self.assertEqual(minimized.splitlines()[0], b"3 2")

    def test_graph_candidates_honor_connected_dag_and_simple_constraints(self):
        data = b"4 4\n1 2 9\n1 3 8\n2 4 7\n3 4 6\n"
        checked = []

        def attempt(candidate, label):
            rows = candidate.splitlines()
            n, m = map(int, rows[0].split())
            edges = [tuple(map(int, row.split()[:2])) for row in rows[1:]]
            self.assertEqual(m, len(edges))
            self.assertEqual(len(edges), len(set(edges)))
            self.assertTrue(all(u != v and 1 <= u <= n and 1 <= v <= n
                                for u, v in edges))
            # This fixture's topological order remains increasing under deletion/reindexing.
            self.assertTrue(all(u < v for u, v in edges))
            adjacency = [[] for _ in range(n + 1)]
            for u, v in edges:
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
            self.assertEqual(len(seen), n)
            checked.append(label)
            return False

        shrink_domain(
            data,
            {"kind": "graph", "directed": True, "dag": True,
             "edge_weights": True, "connectivity": "weak",
             "allow_self_loops": False, "allow_parallel_edges": False},
            attempt,
            lambda: len(checked) < 100,
        )
        self.assertTrue(any(label.startswith("graph:delete-edge") for label in checked))
        self.assertTrue(any(label.startswith("graph:shrink-edge-weight") for label in checked))
        with self.assertRaisesRegex(DomainShrinkError, "constraints"):
            shrink_domain(
                b"2 2\n1 2\n1 2\n",
                {"kind": "graph", "directed": False, "edge_weights": False,
                 "connectivity": "none", "allow_self_loops": False,
                 "allow_parallel_edges": False},
                lambda candidate, label: False,
                lambda: True,
            )

    def test_operation_sequence_repairs_q_and_preserves_prerequisite(self):
        data = (b"5 7\n0 0 0 0 0\n"
                b"add 0 5 9\nquery 0 5\nadd 1 4 3\nset 2 5 7\n"
                b"add 0 2 -4\nquery 2 3\nquery 0 1\n")
        seen = []

        def attempt(candidate, label):
            seen.append(label)
            rows = candidate.splitlines()
            body = rows[2:]
            has_set = any(row.startswith(b"set ") for row in body)
            has_query = any(row.startswith(b"query ") for row in body)
            return has_set and has_query

        minimized, report = shrink_domain(
            data,
            {"kind": "operation-sequence", "initial_array": True,
             "interval_kinds": ["add", "set", "query"], "index_base": 0,
             "right_inclusive": False, "min_operations": 2,
             "preserve_prefix_operations": 1, "preserve_initial_array": True},
            attempt,
            lambda: len(seen) < 120,
        )
        rows = minimized.splitlines()
        n, q = map(int, rows[0].split())
        self.assertEqual(n, 5)
        self.assertEqual(q, len(rows) - 2)
        self.assertEqual(q, 3)
        self.assertEqual(rows[1], b"0 0 0 0 0")
        self.assertEqual(rows[2], b"add 0 5 9")
        self.assertTrue(any(label.startswith("operations:delete-block")
                            for label in report["accepted_transforms"]))
        self.assertTrue(any(label.startswith("operations:delete-one") for label in seen))
        self.assertTrue(any(label.startswith("operations:shrink-interval") for label in seen))
        self.assertTrue(any(label.startswith("operations:shrink-parameter") for label in seen))
        self.assertTrue(any(row.startswith(b"set ") for row in rows[2:]))
        self.assertTrue(any(row.startswith(b"query ") for row in rows[2:]))


if __name__ == "__main__":
    unittest.main()
