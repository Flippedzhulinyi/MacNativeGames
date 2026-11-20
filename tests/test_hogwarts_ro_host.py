"""Exercise local symbol lookup and the unsupported NRO path without game content."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class RoHostTests(unittest.TestCase):
    def test_initialization_and_registration_failure(self):
        source = r'''
#include <stdint.h>
#include <stdlib.h>
void *runtime_hogwarts_ro_override(const char *);
_Noreturn void runtime_fail(const char *msg) { (void)msg; abort(); }
static int target;
void *runtime_symbol(const char *name) {
    return name && name[0] == 'x' && name[1] == '\0' ? &target : NULL;
}
int main(void) {
    uint32_t (*init)(void) = runtime_hogwarts_ro_override("_ZN2nn2ro10InitializeEv");
    uint32_t (*reg)(void *, const void *) =
        runtime_hogwarts_ro_override("_ZN2nn2ro18RegisterModuleInfoEPNS0_16RegistrationInfoEPKv");
    uint32_t (*lookup)(uintptr_t *, const char *) =
        runtime_hogwarts_ro_override("_ZN2nn2ro12LookupSymbolEPmPKc");
    uintptr_t out = 123;
    if (!init || !reg || !lookup || runtime_hogwarts_ro_override("unknown")) return 1;
    if (lookup(&out, "x") || out != (uintptr_t)&target) return 3;
    if (reg(0, 0) == 0 || init() != 0 || reg(0, 0) == 0) return 2;
    if (lookup(&out, "x") || out != (uintptr_t)&target) return 4;
    out = 123;
    if (!lookup(&out, "missing") || out != 123 || !lookup(&out, NULL) ||
        !lookup(&out, "") || !lookup(NULL, "x") || out != 123) return 5;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'test.c').write_text(source)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/ot0/runtime'), str(ROOT / 'games/hogwarts/runtime/ro_host.c'),
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True)
            result = subprocess.run([str(path / 'test')], capture_output=True, text=True, check=True)
            self.assertIn('registration unavailable', result.stderr)


if __name__ == '__main__':
    unittest.main()
