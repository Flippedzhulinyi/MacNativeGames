#include <stdio.h>
#include <stdlib.h>
#include "../games/ot0/runtime/fs_host.c"

_Noreturn void runtime_fail(const char *message) { fprintf(stderr, "%s\n", message); exit(2); }
void runtime_account_uid(uint64_t out[2]) { out[0] = 4; out[1] = 9; }

int main(void) {
    uint64_t local[] = {4, 9}, other[] = {4, 8};
    unsigned char exists = 42;
    if (!own_save_exists(local) || own_save_exists(other) || own_save_exists(NULL)) return 3;
    if (own_save_exists_out(&exists, local) || exists != 1) return 4;
    if (own_save_exists_out(&exists, other) || exists != 0) return 5;
    if (own_save_exists_out(NULL, local) != R_INVALID_ARGUMENT) return 6;
    if (save_exists(TOTK_APPLICATION_ID + 1, local)) return 7;
    return 0;
}
