/* The console shop is unavailable; never report that an accessor was initialized. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint32_t shop_unavailable(void *memory, uint64_t size) {
    (void)memory;
    (void)size;
    fprintf(stderr, "[hogwarts] shop service unavailable on the offline diagnostic host\n");
    return 0x2a2u;
}

void *runtime_hogwarts_shop_override(const char *name) {
    if (!strcmp(name, "_ZN2nn2ec33InitializeForShopServiceAccessorsEPvm")) return shop_unavailable;
    return NULL;
}
