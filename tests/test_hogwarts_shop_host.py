import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class ShopHostTests(unittest.TestCase):
    def test_initialization_reports_unavailable(self):
        source = r'''
#include <stdint.h>
void *runtime_hogwarts_shop_override(const char *);
int main(void) {
    uint32_t (*init)(void *, uint64_t) = runtime_hogwarts_shop_override(
        "_ZN2nn2ec33InitializeForShopServiceAccessorsEPvm");
    if (!init || runtime_hogwarts_shop_override("unknown")) return 1;
    return init(0, 0) ? 0 : 2;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'test.c').write_text(source)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'games/hogwarts/runtime/shop_host.c'),
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], capture_output=True, check=True)


if __name__ == '__main__':
    unittest.main()
