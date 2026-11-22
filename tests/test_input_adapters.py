import copy
import unittest

from oisolver.input_adapters import (
    InputAdapterError,
    inspect_adapted_input,
    parse_adapted_input,
    render_adapted_input,
    shrink_adapted_input,
    validate_adapter_schema,
)


TREE_SCHEMA = {
    "schema_version": 1,
    "test_cases": {"mode": "counted", "allow_case_deletion": True},
    "case": {
        "kind": "tree",
        "header_fields": ["n"],
        "size_field": "n",
        "index_base": 0,
        "node_weights": True,
        "edges": {
            "fields": ["weight", "to", "from"],
            "u_field": "from",
            "v_field": "to",
            "weight_field": "weight",
        },
    },
}


class DeclarativeInputAdapters(unittest.TestCase):
    def test_counted_zero_indexed_weighted_tree_round_trip(self):
        data = (
            b"2\n"
            b"4\n5 6 7 8\n9 1 0\n3 2 1\n4 3 1\n"
            b"2\n10 11\n1 1 0\n"
        )
        cases = parse_adapted_input(data, TREE_SCHEMA)
        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0].node_weights, [5, 6, 7, 8])
        self.assertEqual(cases[0].edges[0], {"weight": 9, "to": 1, "from": 0})
        headers_before = [dict(case.header) for case in cases]
        self.assertEqual(render_adapted_input(cases, TREE_SCHEMA), data)
        self.assertEqual([case.header for case in cases], headers_before)
        inspection = inspect_adapted_input(data, TREE_SCHEMA)
        self.assertTrue(inspection["valid"])
        self.assertEqual(inspection["cases"], 2)
        self.assertEqual(inspection["case_summaries"][0]["edges"], 3)

    def test_graph_supports_unweighted_reordered_endpoints(self):
        schema = {
            "schema_version": 1,
            "case": {
                "kind": "graph",
                "header_fields": ["m", "n"],
                "size_field": "n",
                "edge_count_field": "m",
                "index_base": 1,
                "directed": True,
                "dag": True,
                "connectivity": "none",
                "allow_self_loops": False,
                "allow_parallel_edges": False,
                "edges": {
                    "fields": ["destination", "source"],
                    "u_field": "source",
                    "v_field": "destination",
                },
            },
        }
        data = b"3 4\n2 1\n3 1\n4 3\n"
        case = parse_adapted_input(data, schema)[0]
        self.assertEqual(case.header, {"m": 3, "n": 4})
        self.assertEqual(case.edges[2], {"destination": 4, "source": 3})
        self.assertEqual(render_adapted_input([case], schema), data)

    def test_mixed_arity_operations_keep_declared_indexing(self):
        schema = {
            "schema_version": 1,
            "case": {
                "kind": "operation-sequence",
                "header_fields": ["n", "q"],
                "size_field": "n",
                "operation_count_field": "q",
                "index_base": 1,
                "initial_array": True,
                "interval_ops": ["add", "query", "set"],
                "right_inclusive": True,
                "min_operations": 1,
            },
        }
        data = (
            b"4 4\n1 2 3 4\n"
            b"add 1 4 8\nquery 2 3\nflip 7\nset 1 1 -4\n"
        )
        attempts = []

        def accept(candidate, label):
            reparsed = parse_adapted_input(candidate, schema)
            attempts.append((label, reparsed[0].operations))
            return True

        minimized, report = shrink_adapted_input(data, schema, accept, lambda: True)
        case = parse_adapted_input(minimized, schema)[0]
        self.assertEqual(len(case.operations), 1)
        self.assertGreater(len(attempts), 0)
        self.assertEqual(report["case_reports"][0]["kind"], "operation-sequence")
        # Canonical 0-based conversion is internal; rendered endpoints stay 1-based.
        if case.operations[0][0] in {"add", "query", "set"}:
            self.assertGreaterEqual(int(case.operations[0][1]), 1)
            self.assertGreaterEqual(int(case.operations[0][2]), 1)

    def test_integer_grid_shrinks_rows_columns_and_cells(self):
        schema = {
            "schema_version": 1,
            "case": {
                "kind": "grid",
                "header_fields": ["rows", "columns"],
                "size_field": "rows",
                "columns_field": "columns",
                "cell_format": "tokens",
                "cell_type": "integer",
                "min_rows": 1,
                "min_columns": 1,
            },
        }
        data = b"3 3\n9 8 7\n6 5 4\n3 2 1\n"
        seen = []

        def accept(candidate, label):
            parse_adapted_input(candidate, schema)
            seen.append(label)
            return True

        minimized, report = shrink_adapted_input(data, schema, accept, lambda: True)
        case = parse_adapted_input(minimized, schema)[0]
        self.assertEqual((len(case.grid), len(case.grid[0])), (1, 1))
        self.assertEqual(case.grid[0][0], "0")
        self.assertTrue(any("delete-rows" in label for label in seen))
        self.assertTrue(any("delete-columns" in label for label in seen))
        self.assertEqual(report["case_reports"][0]["rows"], 1)

    def test_counted_cases_are_deleted_independently_before_case_shrink(self):
        schema = copy.deepcopy(TREE_SCHEMA)
        schema["case"]["node_weights"] = False
        data = b"3\n2\n9 0 1\n1\n2\n2 0 1\n"
        accepted = []

        def accept(candidate, label):
            parse_adapted_input(candidate, schema)
            if label.startswith("adapter:delete-cases"):
                accepted.append(label)
                return True
            return False

        minimized, report = shrink_adapted_input(data, schema, accept, lambda: True)
        self.assertEqual(len(parse_adapted_input(minimized, schema)), 1)
        self.assertEqual(report["original_cases"], 3)
        self.assertEqual(report["minimized_cases"], 1)
        self.assertEqual(report["accepted_case_deletions"], accepted)

    def test_schema_typos_and_invalid_index_fail_closed(self):
        typo = copy.deepcopy(TREE_SCHEMA)
        typo["case"]["index_bsae"] = 0
        with self.assertRaisesRegex(InputAdapterError, "unknown fields"):
            validate_adapter_schema(typo)
        invalid = copy.deepcopy(TREE_SCHEMA)
        invalid["case"]["index_base"] = 2
        with self.assertRaisesRegex(InputAdapterError, "0 or 1"):
            parse_adapted_input(b"1\n1\n5\n", invalid)
        with self.assertRaisesRegex(InputAdapterError, "outside"):
            parse_adapted_input(b"1\n2\n1 2\n7 0 2\n", TREE_SCHEMA)


if __name__ == "__main__":
    unittest.main()
