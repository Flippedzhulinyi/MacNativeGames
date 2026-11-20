/* The console save-data manager thumbnail is not stored by the diagnostic host. */
#include "fs_host.h"
#include "runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <stdatomic.h>
#include <string.h>

static uint32_t store_thumbnail(const uint64_t *uid, const void *image, uint64_t size) {
    uint64_t local[2];
    if (!uid || (!image && size)) return 0x7c67;
    runtime_account_uid(local);
    if (uid[0] != local[0] || uid[1] != local[1]) return 0x7c67;
    static atomic_flag logged = ATOMIC_FLAG_INIT;
    if (!atomic_flag_test_and_set(&logged))
        fprintf(stderr, "[hogwarts] console save thumbnail ignored: no console data-management screen\n");
    return 0;
}

static uint32_t network_service_available(unsigned char *out, const void *handle) {
    if (!out || !handle) return 0x7c67;
    uint32_t (*get_user_id)(uint64_t *, const void *) =
        runtime_account_override("_ZN2nn7account9GetUserIdEPNS0_3UidERKNS0_10UserHandleE");
    if (!get_user_id) runtime_fail("local account GetUserId override missing");
    uint64_t uid[2];
    uint32_t result = get_user_id(uid, handle);
    if (!result) *out = 0;
    return result;
}

void *runtime_hogwarts_account_override(const char *name) {
    if (!strcmp(name, "_ZN2nn7account27StoreSaveDataThumbnailImageERKNS0_3UidEPKvm")) return store_thumbnail;
    if (!strcmp(name, "_ZN2nn7account32IsNetworkServiceAccountAvailableEPbRKNS0_10UserHandleE")) return network_service_available;
    return NULL;
}
