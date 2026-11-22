import os
from pathlib import Path
import tempfile
import unittest

from oisolver.style import (calibrate_cpp_style, clang_ast_signature,
                            evaluate_cpp_files, evaluate_cpp_patch)


FIXTURE = Path(__file__).parent / "fixtures" / "style"
CALIBRATION = Path(__file__).parent / "fixtures" / "style-calibration" / "corpus.json"


class CppStyleMetrics(unittest.TestCase):
    def test_one_token_fix_scores_as_minimal_and_preserves_style(self):
        result = evaluate_cpp_files(
            FIXTURE / "original.cpp", FIXTURE / "expected.cpp",
            [("upper_bound", "lower_bound")],
        )
        self.assertEqual(result["token"]["edit_distance"], 1)
        self.assertEqual(result["ast"]["lightweight_backend"], "structural-token-tree")
        self.assertEqual(result["lines"]["nonessential_changed"], 0)
        self.assertGreater(result["preservation"]["identifiers"], 0.9)
        self.assertEqual(result["preservation"]["variable_names"], 1.0)
        self.assertEqual(result["preservation"]["macros"], 1.0)
        self.assertEqual(result["preservation"]["fast_io"], 1.0)
        self.assertTrue(result["gate_passed"])
        self.assertGreater(result["score"], 98)

    @unittest.skipUnless(os.name == "posix", "executable fixture requires POSIX")
    def test_optional_clang_json_ast_backend_is_parsed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "clang++"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'kind':'TranslationUnitDecl','inner':[{'kind':'FunctionDecl'}]}))\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            source = root / "x.cpp"
            source.write_text("int main(){}\n", encoding="utf-8")
            result = clang_ast_signature(source, str(fake))
            self.assertTrue(result["available"])
            self.assertEqual(result["nodes"], ["TranslationUnitDecl", "FunctionDecl"])

    def test_realistic_repair_corpus_calibrates_zero_false_positive_threshold(self):
        result = calibrate_cpp_style(CALIBRATION)
        self.assertEqual(result["samples"], 12)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["calibration_passed"])
        self.assertEqual(result["selected_threshold"], 0.10)
        selected = next(
            item for item in result["threshold_sweep"]
            if item["threshold"] == result["selected_threshold"]
        )
        self.assertEqual(selected["false_positive_count"], 0)
        self.assertEqual(selected["false_negative_count"], 0)
        stricter = next(item for item in result["threshold_sweep"]
                        if item["threshold"] == 0.05)
        self.assertGreater(stricter["false_positive_count"], 0)
        self.assertFalse(result["missing_tags"])
        self.assertTrue(result["required_warnings_present"])

    def test_destructive_rewrite_triggers_explicit_style_warnings(self):
        before = """#include<bits/stdc++.h>
using namespace std;
#define int long long
int a[1000];
signed main(){
    ios::sync_with_stdio(false);cin.tie(nullptr);
    int n;cin>>n;
    for(int i=0;i<n;i++) cin>>a[i];
}
"""
        after = """#include <bits/stdc++.h>
using namespace std;
int main() {
  int count;
  std::cin >> count;
  std::vector<long long> values(count);
  for (int index = 0; index < count; ++index) std::cin >> values[index];
}
"""
        result = evaluate_cpp_patch(before, after)
        codes = {item["code"] for item in result["warnings"]}
        self.assertIn("IDENTIFIERS_NOT_PRESERVED", codes)
        self.assertIn("VARIABLE_NAMES_NOT_PRESERVED", codes)
        self.assertIn("MACRO_CHANGED_OR_REMOVED", codes)
        self.assertIn("FAST_IO_REMOVED", codes)
        self.assertIn("GLOBAL_ARRAY_REPLACED_BY_VECTOR", codes)
        self.assertIn("NONESSENTIAL_LINE_CHANGES", codes)
        self.assertFalse(result["gate_passed"])
        self.assertLess(result["score"], 90)


if __name__ == "__main__":
    unittest.main()
