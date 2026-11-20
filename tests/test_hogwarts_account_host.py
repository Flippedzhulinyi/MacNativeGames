"""Verify the console-only thumbnail override validates the local account."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc'), 'C compiler not available')
class AccountHostTests(unittest.TestCase):
    def test_store_thumbnail(self):
        source = r'''
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
void *runtime_hogwarts_account_override(const char *);
void runtime_account_uid(uint64_t out[2]) { out[0] = 4; out[1] = 9; }
_Noreturn void runtime_fail(const char *message) { (void)message; abort(); }
static uint32_t get_id(uint64_t *out, const void *handle) {
    if (*(const int *)handle != 5) return 0x7c67;
    out[0] = 4; out[1] = 9; return 0;
}
void *runtime_account_override(const char *name) {
    return strcmp(name, "_ZN2nn7account9GetUserIdEPNS0_3UidERKNS0_10UserHandleE") ? 0 : get_id;
}
int main(void) {
    uint32_t (*store)(const uint64_t *, const void *, uint64_t) =
        runtime_hogwarts_account_override("_ZN2nn7account27StoreSaveDataThumbnailImageERKNS0_3UidEPKvm");
    uint64_t good[2] = {4,9}, bad[2] = {4,8};
    char image = 0;
    if (!store || runtime_hogwarts_account_override("unknown")) return 1;
    if (store(good,&image,1) != 0) return 2;
    if (!store(bad,&image,1) || !store(0,&image,1) || !store(good,0,1)) return 3;
    uint32_t (*available)(unsigned char *, const void *) = runtime_hogwarts_account_override(
        "_ZN2nn7account32IsNetworkServiceAccountAvailableEPbRKNS0_10UserHandleE");
    int handle = 5, invalid = 6;
    unsigned char result = 1;
    if (!available || available(&result, &handle) || result) return 4;
    result = 1;
    if (!available(&result, &invalid) || result != 1 || !available(0, &handle) || !available(&result, 0)) return 5;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'test.c').write_text(source)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'games/ot0/runtime'), str(ROOT / 'games/hogwarts/runtime/account_host.c'),
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], capture_output=True, check=True)


if __name__ == '__main__':
    unittest.main()
