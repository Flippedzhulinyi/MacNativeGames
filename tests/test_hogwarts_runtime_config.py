"""The experimental target must not use the Octopath title identity."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / 'games/ot0/runtime/game_version.h'


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class RuntimeConfigTests(unittest.TestCase):
    def macros(self, define):
        result = subprocess.run(['cc', '-dM', '-E', '-x', 'c', f'-D{define}', str(HEADER)],
                                check=True, capture_output=True, text=True)
        return result.stdout

    def test_hogwarts_identity(self):
        macros = self.macros('HOGWARTS_EXPERIMENTAL')
        self.assertIn('#define GAME_TITLE_ID 0x0100f7e00c70e000ULL', macros)
        self.assertIn('#define TOTK_GAME_DIR "hogwarts"', macros)
        self.assertNotIn('#define GAME_OT0 ', macros)
        self.assertNotIn('#define GAME_MAX_TICK_RATE ', macros)

    def test_octopath_identity_is_unchanged(self):
        macros = self.macros('OT0_GAME_V105')
        self.assertIn('#define GAME_TITLE_ID 0x01005270232f2000ULL', macros)
        self.assertIn('#define TOTK_GAME_DIR "v105"', macros)
        self.assertIn('#define GAME_OT0 1', macros)
        self.assertIn('#define GAME_MAX_TICK_RATE 0x25f8940', macros)


if __name__ == '__main__':
    unittest.main()
