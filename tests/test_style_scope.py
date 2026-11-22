from pathlib import Path
import unittest


ROOT = Path(__file__).parent / "fixtures" / "style"


class MinimalPatchGolden(unittest.TestCase):
    def test_reference_fix_changes_only_the_required_token(self):
        before = (ROOT / "original.cpp").read_bytes()
        after = (ROOT / "expected.cpp").read_bytes()
        self.assertEqual(before.count(b"upper_bound"), 1)
        self.assertEqual(after, before.replace(b"upper_bound", b"lower_bound", 1))
        self.assertEqual(len(before), len(after))
        differences = [index for index, (left, right) in enumerate(zip(before, after))
                       if left != right]
        self.assertEqual(len(differences), 3)  # Only the upper/lower prefix bytes differ.
        # Macros, layout, global style, I/O, names, and all unrelated bytes stay exact.
        self.assertIn(b"#define int long long", after)
        self.assertIn(b"ios::sync_with_stdio(false);cin.tie(nullptr);", after)


if __name__ == "__main__":
    unittest.main()
