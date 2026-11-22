import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

from oisolver.catalog import CatalogClient, CatalogError, default_extension_path, resolve_catalog


IDS = [
    "oiwiki.misc.cdq-divide",
    "oiwiki.dp.tree",
    "oiwiki.ds.seg",
    "oiwiki.ds.persistent-seg",
    "oiwiki.ds.seg.dynamic",
    "oiwiki.contest.common-tricks.differential-testing",
]


class CatalogBridge(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        catalog = {
            "schema_version": 1,
            "source": {"repository": "https://github.com/OI-wiki/OI-wiki",
                       "revision": "1" * 40},
            "entries": [{"id": item, "name": item, "aliases": [],
                         "category": ["fixture"], "source_url": "https://example.test/"}
                        for item in IDS],
        }
        (self.root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        (self.root / "catalog.py").write_text(textwrap.dedent("""
            import argparse, json
            from pathlib import Path
            p = argparse.ArgumentParser()
            p.add_argument('--catalog', required=True)
            p.add_argument('command')
            p.add_argument('rest', nargs='*')
            a = p.parse_args()
            d = json.loads(Path(a.catalog).read_text(encoding='utf-8'))
            if a.command == 'validate':
                out = {'entries': len(d['entries']), 'fixture': True}
            elif a.command == 'get':
                out = next(x for x in d['entries'] if x['id'] == a.rest[0])
            elif a.command == 'search':
                query = a.rest[0] if a.rest else ''
                rows = [x for x in d['entries'] if query.casefold() in (x['id']+' '+x['name']).casefold()]
                out = {'total': len(rows), 'entries': rows}
            elif a.command == 'stats':
                out = {'entries': len(d['entries'])}
            elif a.command == 'categories':
                out = {'fixture': len(d['entries'])}
            elif a.command == 'levels':
                out = {'scale': []}
            elif a.command == 'tag':
                out = {'tags': [], 'entries': []}
            else:
                raise SystemExit(2)
            print(json.dumps(out))
        """), encoding="utf-8")

    def test_query_delegates_and_joins_by_foreign_key(self):
        client = CatalogClient(str(self.root), python=sys.executable)
        result = client.query("get", ["oiwiki.misc.cdq-divide"])
        self.assertEqual(result["catalog"]["id"], "oiwiki.misc.cdq-divide")
        self.assertEqual(result["solver_extensions"][0]["algorithm_id"],
                         "oiwiki.misc.cdq-divide")
        self.assertEqual(len(result["solver_extensions"][0]["claims"]), 2)
        self.assertEqual(result["provenance"]["source_revision"], "1" * 40)
        self.assertEqual(len(result["provenance"]["catalog_sha256"]), 64)
        self.assertIn("not a correctness certificate", result["notice"])

    def test_validate_checks_upstream_and_overlay(self):
        result = CatalogClient(str(self.root), python=sys.executable).validate()
        self.assertTrue(result["extensions"]["foreign_keys_valid"])
        self.assertEqual(result["extensions"]["entries"], 6)
        self.assertTrue(result["upstream"]["fixture"])

    def test_mutating_commands_are_not_exposed(self):
        client = CatalogClient(str(self.root), python=sys.executable)
        with self.assertRaisesRegex(CatalogError, "not read-only"):
            client.delegate("update", [])

    def test_requires_actual_script_and_data(self):
        (self.root / "catalog.py").unlink()
        with self.assertRaisesRegex(CatalogError, "incomplete"):
            resolve_catalog(str(self.root))

    def test_unknown_extension_foreign_key_fails_closed(self):
        extension = json.loads(default_extension_path().read_text(encoding="utf-8"))
        extension["entries"][0]["algorithm_id"] = "missing.algorithm"
        path = self.root / "extension.json"
        path.write_text(json.dumps(extension), encoding="utf-8")
        with self.assertRaisesRegex(CatalogError, "unknown CPscore IDs"):
            CatalogClient(str(self.root), extension_path=path, python=sys.executable)

    @unittest.skipUnless(os.environ.get("CPSCORE_CATALOG"),
                         "set CPSCORE_CATALOG for the real CPscore integration check")
    def test_real_cpscore_catalog(self):
        client = CatalogClient(os.environ["CPSCORE_CATALOG"])
        validation = client.validate()
        self.assertGreaterEqual(validation["upstream"]["entries"], 600)
        result = client.query("search", ["CDQ 分治", "--limit", "5"])
        ids = [entry["id"] for entry in result["catalog"]["entries"]]
        self.assertIn("oiwiki.misc.cdq-divide", ids)
        self.assertTrue(result["solver_extensions"])


if __name__ == "__main__":
    unittest.main()
