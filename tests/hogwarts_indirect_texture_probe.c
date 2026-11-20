#include "nvn_indirect_texture.h"
#include <stdio.h>
#include <string.h>

static int resolve(void *context, nvn_indirect_texture_ids ids, uint64_t *texture, uint64_t *sampler) {
    (void)context;
    if (ids.texture_id == 9) return 0;
    *texture = ids.texture_id + 0x100;
    *sampler = ids.sampler_id + 0x1000;
    return 1;
}

static int reject(const char *name, const char *type) {
    nvn_indirect_texture v = {0};
    return nvn_indirect_texture_decode(name, type, &v);
}
int main(void) {
    nvn_indirect_texture v = {0};
    nvn_indirect_single_texture single = {0};
    if (!nvn_indirect_single_texture_decode("fp_t_cb196613_10568000", "texture2d<float>", &single) ||
        single.uniform_slot != 2 || single.uniform_byte_offset != 0 || single.sampler_slot != 0 || single.sampler)
        return 12;
    if (!nvn_indirect_single_texture_decode("fp_t_cb196613_10570002Smplr", "sampler", &single) ||
        single.uniform_slot != 2 || single.uniform_byte_offset != 8 || single.sampler_slot != 1 || !single.sampler)
        return 13;
    nvn_indirect_single_texture saved = single;
    if (nvn_indirect_single_texture_decode("fp_t_cb196613_10570002", "texture3d<float>", &single) ||
        nvn_indirect_single_texture_decode("fp_t_cb196613_10570002Smplr", "texture2d<float>", &single) ||
        nvn_indirect_single_texture_decode("fp_t_cb131077_10570002", "texture2d<float>", &single) ||
        nvn_indirect_single_texture_decode("fp_t_cb196610_10570002", "texture2d<float>", &single) ||
        nvn_indirect_single_texture_decode("fp_t_cb196613_20570002", "texture2d<float>", &single) ||
        nvn_indirect_single_texture_decode("fp_t_cb196613_10570002bad", "texture2d<float>", &single) ||
        nvn_indirect_single_texture_decode(NULL, "texture2d<float>", &single) ||
        nvn_indirect_single_texture_decode("fp_t_cb196613_10570002", "texture2d<float>", NULL) ||
        memcmp(&single, &saved, sizeof single)) return 14;
    nvn_indirect_single_sampler indirect_sampler = {0};
    if (!nvn_indirect_single_sampler_decode("fp_t_cb393218_10028166", "texture2d<float>", &indirect_sampler) ||
        indirect_sampler.uniform_slot != 2 || indirect_sampler.uniform_byte_offset != 0x28 ||
        indirect_sampler.sampler_slot != 6 || indirect_sampler.reflected_texture_slot != 1 || indirect_sampler.sampler ||
        !nvn_indirect_single_sampler_decode("fp_t_cb393218_10028166Smplr", "sampler", &indirect_sampler) ||
        !indirect_sampler.sampler) return 15;
    nvn_indirect_single_sampler sampler_saved = indirect_sampler;
    if (nvn_indirect_single_sampler_decode("fp_t_cb393218_10028166Smplr", "texture2d<float>", &indirect_sampler) ||
        nvn_indirect_single_sampler_decode("fp_t_cb196613_10028166", "texture2d<float>", &indirect_sampler) ||
        nvn_indirect_single_sampler_decode("fp_t_cb393218_20028166", "texture2d<float>", &indirect_sampler) ||
        nvn_indirect_single_sampler_decode("fp_t_cb393218_1002C166", "texture2d<float>", &indirect_sampler) ||
        nvn_indirect_single_sampler_decode("fp_t_cb393218_10028166junk", "texture2d<float>", &indirect_sampler) ||
        memcmp(&indirect_sampler, &sampler_saved, sizeof indirect_sampler)) return 16;
    /* texture c5, sampler c2 + 0x578, separate handle */
    if (!nvn_indirect_texture_decode("fp_t3d_cb196613_10578000", "array<texture3d<float>, 32>", &v) ||
        v.uniform_slot != 2 || v.sampler_slot != 2 || v.count != 32 || v.sampler) return 1;
    if (!nvn_indirect_texture_decode("fp_t3d_cb196613_10578000Smplr", "array<sampler, 32>", &v) ||
        v.uniform_slot != 2 || v.sampler_slot != 2 || v.count != 32 || !v.sampler) return 2;
    if (reject("fp_t3d_cb196613_10578001", "array<texture3d<float>, 32>") ||
        reject("fp_t3d_cb196613_20578000", "array<texture3d<float>, 32>") ||
        reject("fp_t3d_cb196613_10578000", "array<texture3d<float>, 33>") ||
        reject("fp_t3d_cb196613_10578000", "array<texture3d<float>, 0>") ||
        reject("fp_t3d_cb196613_10578000Smplr", "array<texture3d<float>, 32>") ||
        reject("fp_t3d_cb196613_10578000", "array<texture2d<float>, 32>") ||
        reject("fp_t2d_cb196613_10578000", "array<texture3d<float>, 32>") ||
        reject("fp_t2d_cb196613_10578000Smplr", "array<sampler, 32>") ||
        reject("fp_t_cb196613_10578000", "array<texture3d<float>, 32>") ||
        reject("fp_t3d_cb131077_10578000", "array<texture3d<float>, 32>") ||
        reject("fp_t3d_cb196613_10560000", "array<texture3d<float>, 32>") ||
        reject("fp_t3d_cb196613_10578000bogus", "array<texture3d<float>, 32>") ||
        reject("fp_t3d_cb999999999999999999999999_10578000", "array<texture3d<float>, 32>") ||
        reject("fp_t3d_cb196613_10578000", "array<texture3d<float>, 32>junk") ||
        reject(NULL, NULL)) return 3;
    if (!nvn_indirect_cube_decode("fp_tcube_cb196617_105A0000", "array<texturecube<float>, 32>", &v) ||
        v.uniform_slot != 6 || v.sampler_slot != 7 || v.count != 32 || v.sampler ||
        !nvn_indirect_cube_decode("fp_tcube_cb196617_105A0000Smplr", "array<sampler, 32>", &v) ||
        !v.sampler ||
        nvn_indirect_cube_decode("fp_tcube_cb196617_105A0000", "array<texture3d<float>, 32>", &v) ||
        nvn_indirect_cube_decode("fp_tcube_cb196617_105A0001", "array<texturecube<float>, 32>", &v) ||
        nvn_indirect_texture_decode("fp_tcube_cb196617_105A0000", "array<texturecube<float>, 32>", &v))
        return 17;
    if (!nvn_indirect_2d_decode("fp_t2d_cb196615_10570000", "array<texture2d<float>, 32>", &v) ||
        v.uniform_slot != 4 || v.sampler_slot != 1 || v.count != 32 || v.sampler ||
        !nvn_indirect_2d_decode("fp_t2d_cb196615_10570000Smplr", "array<sampler, 32>", &v) ||
        !v.sampler ||
        nvn_indirect_2d_decode("fp_t2d_cb196615_10570000", "array<texturecube<float>, 32>", &v) ||
        nvn_indirect_2d_decode("fp_t2d_cb196615_10570001", "array<texture2d<float>, 32>", &v))
        return 18;
    uint8_t storage[1 + 8 * 32] = {0};
    uint8_t *snapshot = storage + 1;
    for (uint32_t i = 0; i < 32; i++) {
        uint32_t handle = i + 1;
        if (i == 31) handle |= 0x40000000u;
        memcpy(snapshot + i * 8, &handle, sizeof handle);
        memset(snapshot + i * 8 + 4, 0xff, 4);
    }
    nvn_indirect_texture_ids ids[32] = {{0}};
    if (!nvn_indirect_texture_unpack(snapshot, 31 * 8 + 4, 32, 0x12300000u, ids)) return 4;
    for (uint32_t i = 0; i < 32; i++) {
        if (ids[i].texture_id != i + 1 ||
            ids[i].sampler_id != (i == 31 ? 0x523u : 0x123u)) return 5;
    }
    nvn_indirect_texture_ids before[32];
    memcpy(before, ids, sizeof ids);
    if (nvn_indirect_texture_unpack(snapshot, 31 * 8 + 3, 32, 0, ids) ||
        nvn_indirect_texture_unpack(snapshot, sizeof storage - 1, 0, 0, ids) ||
        nvn_indirect_texture_unpack(snapshot, sizeof storage - 1, 33, 0, ids) ||
        nvn_indirect_texture_unpack(NULL, sizeof storage - 1, 32, 0, ids) ||
        nvn_indirect_texture_unpack(snapshot, sizeof storage - 1, 32, 0, NULL) ||
        memcmp(before, ids, sizeof ids)) return 6;
    uint64_t slots[80], unchanged[80];
    for (unsigned i = 0; i < 80; i++) slots[i] = 0x1234;
    memcpy(unchanged, slots, sizeof slots);
    unsigned failed = 99;
    if (nvn_indirect_texture_bind(snapshot, 252, 32, 0, slots, 80, 12, 44,
                                  resolve, NULL, &failed) != NVN_INDIRECT_RESOURCE_UNAVAILABLE ||
        failed != 8 || memcmp(slots, unchanged, sizeof slots)) return 7;
    uint32_t replacement = 10;
    memcpy(snapshot + 8 * 8, &replacement, sizeof replacement);
    if (nvn_indirect_texture_bind(snapshot, 252, 32, 0x12300000, slots, 80, 12, 44,
                                  resolve, NULL, &failed) != NVN_INDIRECT_OK) return 8;
    if (slots[12] != 0x101 || slots[20] != 0x10a ||
        slots[44] != 0x1123 || slots[75] != 0x1523 ||
        slots[11] != 0x1234 || slots[76] != 0x1234) return 9;
    memcpy(unchanged, slots, sizeof slots);
    if (nvn_indirect_texture_bind(snapshot, 252, 32, 0, slots, 80, 12, 43, resolve, NULL, NULL) != NVN_INDIRECT_INVALID ||
        nvn_indirect_texture_bind(snapshot, 252, 32, 0, slots, 75, 12, 44, resolve, NULL, NULL) != NVN_INDIRECT_INVALID ||
        nvn_indirect_texture_bind(snapshot, 251, 32, 0, slots, 80, 12, 44, resolve, NULL, NULL) != NVN_INDIRECT_INVALID ||
        nvn_indirect_texture_bind(snapshot, 252, 32, 0, slots, 80, 12, 44, NULL, NULL, NULL) != NVN_INDIRECT_INVALID ||
        memcmp(slots, unchanged, sizeof slots)) return 10;
    nvn_indirect_scalar_binding scalar_bindings[3] = {
        {{1, 2}, 10, 11}, {{9, 3}, 15, 16}, {{3, 4}, 20, 21}};
    failed = 99;
    if (nvn_indirect_scalar_bind_ids(scalar_bindings, 3, slots, 80, resolve, NULL, &failed) !=
            NVN_INDIRECT_RESOURCE_UNAVAILABLE || failed != 1 || memcmp(slots, unchanged, sizeof slots))
        return 18;
    scalar_bindings[1].ids.texture_id = 2;
    if (nvn_indirect_scalar_bind_ids(scalar_bindings, 3, slots, 80, resolve, NULL, &failed) != NVN_INDIRECT_OK ||
        slots[10] != 0x101 || slots[11] != 0x1002 || slots[15] != 0x102 || slots[16] != 0x1003 ||
        slots[20] != 0x103 || slots[21] != 0x1004 || slots[22] != unchanged[22]) return 19;
    memcpy(unchanged, slots, sizeof slots);
    scalar_bindings[1].sampler_slot = 10;
    if (nvn_indirect_scalar_bind_ids(scalar_bindings, 3, slots, 80, resolve, NULL, &failed) != NVN_INDIRECT_INVALID ||
        nvn_indirect_scalar_bind_ids(scalar_bindings, 65, slots, 80, resolve, NULL, &failed) != NVN_INDIRECT_INVALID ||
        memcmp(slots, unchanged, sizeof slots)) return 20;
    if (nvn_indirect_range_relation(100, 8, 1, 107, 3, 2) != NVN_INDIRECT_RANGE_OVERLAP ||
        nvn_indirect_range_relation(107, 3, 2, 100, 8, 1) != NVN_INDIRECT_RANGE_OVERLAP ||
        nvn_indirect_range_relation(100, 8, 1, 108, 3, 2) != NVN_INDIRECT_RANGE_DISJOINT ||
        nvn_indirect_range_relation(100, 8, 1, 200, 3, 1) != NVN_INDIRECT_RANGE_OVERLAP ||
        nvn_indirect_range_relation(0, 0, 1, 0, 0, 1) != NVN_INDIRECT_RANGE_OVERLAP ||
        nvn_indirect_range_relation(0, 8, 0, 100, 8, 0) != NVN_INDIRECT_RANGE_UNKNOWN ||
        nvn_indirect_range_relation(100, 0, 0, 100, 8, 0) != NVN_INDIRECT_RANGE_UNKNOWN ||
        nvn_indirect_range_relation(UINT64_MAX - 1, 3, 0, 100, 8, 0) != NVN_INDIRECT_RANGE_UNKNOWN ||
        nvn_indirect_range_relation(UINT64_MAX - 1, 2, 0, UINT64_MAX, 1, 0) != NVN_INDIRECT_RANGE_OVERLAP)
        return 11;
    return 0;
}
