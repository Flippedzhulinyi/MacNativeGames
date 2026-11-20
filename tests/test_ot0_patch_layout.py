"""Branch-reachable NSO patch layout boundaries."""
import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'games/ot0/third_party/d2r/patch_layout.py'
spec = importlib.util.spec_from_file_location('ot0_patch_layout', PATH)
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class PatchLayoutTests(unittest.TestCase):
    def test_existing_after_image_layout(self):
        self.assertEqual(layout.patch_layout(0x10001, 0x10000),
                         (0x20000, 0, 0x2000000))

    def test_existing_before_image_layout(self):
        self.assertEqual(layout.patch_layout(0x9000000, 0x5000000),
                         (-0x2000000, 0x2000000, 0x2000000))

    def test_large_text_uses_smaller_aligned_reserve(self):
        patch, image, reserve = layout.patch_layout(178000000, 112906112)
        self.assertEqual(patch, -reserve)
        self.assertEqual(image, reserve)
        self.assertEqual(reserve % 0x4000, 0)
        self.assertLess(reserve + 112906112, 1 << 27)
        self.assertGreater(reserve, 0)

    def test_positive_branch_limit_is_exclusive(self):
        _, _, reserve = layout.patch_layout(0x9000000, 0x7000000)
        self.assertLess(0x7000000 + reserve, 1 << 27)

    def test_no_reachable_page(self):
        with self.assertRaisesRegex(ValueError, 'branch-reachable'):
            layout.patch_layout(0x9000000, (1 << 27) - 0x3fff)


if __name__ == '__main__':
    unittest.main()
