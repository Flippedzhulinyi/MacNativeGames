#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* Ryujinx BindlessToArray emits a zero-based array of 64-bit texture handles.
   The supported form uses a separate, fixed sampler from driver bank c2. */
typedef struct {
    uint16_t uniform_slot;
    uint16_t sampler_slot;
    uint16_t count;
    uint8_t sampler;
} nvn_indirect_texture;

typedef struct {
    uint32_t texture_id, sampler_id;
} nvn_indirect_texture_ids;

typedef struct {
    uint16_t uniform_slot, uniform_byte_offset, sampler_slot;
    uint8_t sampler;
} nvn_indirect_single_texture;

typedef struct {
    uint16_t uniform_slot, uniform_byte_offset, sampler_slot, reflected_texture_slot;
    uint8_t sampler;
} nvn_indirect_single_sampler;

static inline int nvn_indirect_single_sampler_decode(const char *name, const char *type,
                                                      nvn_indirect_single_sampler *out) {
    if (!name || !type || !out || strlen(name) < 8 ||
        !((name[0] == 'v' || name[0] == 'f' || name[0] == 'c') &&
          name[1] == 'p' && !strncmp(name + 2, "_t_cb", 5))) return 0;
    const char *digits = name + 7;
    if (*digits < '0' || *digits > '9') return 0;
    char *end;
    unsigned long slots = strtoul(digits, &end, 10);
    if (slots > UINT32_MAX || *end != '_') return 0;
    const char *hex = end + 1;
    if (!((*hex >= '0' && *hex <= '9') || (*hex >= 'A' && *hex <= 'F'))) return 0;
    unsigned long handle = strtoul(hex, &end, 16);
    if (handle > UINT32_MAX) return 0;
    int sampler = strcmp(end, "Smplr") == 0;
    if (*end && !sampler) return 0;
    unsigned texture_bank = (unsigned)slots & 0xffffu;
    unsigned sampler_bank_plus_one = (unsigned)slots >> 16;
    /* The low offset belongs to c2 and the high offset to the user bank;
       the separate handles are ORed, so c2 can contain the sampler bits. */
    unsigned driver_byte = ((unsigned)handle & 0x3fffu) * 4u;
    unsigned uniform_byte = (((unsigned)handle >> 14) & 0x3fffu) * 4u;
    if (texture_bank != 2 || sampler_bank_plus_one < 4 || sampler_bank_plus_one > 17 ||
        ((unsigned)handle >> 28) != 1 ||
        driver_byte < 0x568 || driver_byte >= 0x568 + 128 * 8 || (driver_byte - 0x568) % 8 ||
        uniform_byte < 0x20 || uniform_byte >= 0x120 || (uniform_byte - 0x20) % 8 ||
        strcmp(type, sampler ? "sampler" : "texture2d<float>")) return 0;
    *out = (nvn_indirect_single_sampler){(uint16_t)(sampler_bank_plus_one - 4),
        (uint16_t)uniform_byte, (uint16_t)((driver_byte - 0x568) / 8),
        (uint16_t)((uniform_byte - 0x20) / 8), (uint8_t)sampler};
    return 1;
}

/* A fixed 2D texture handle in a user uniform bank with a separate c2 sampler.
   Decoding this form does not mean replay supports or can safely bind it. */
static inline int nvn_indirect_single_texture_decode(const char *name, const char *type,
                                                      nvn_indirect_single_texture *out) {
    if (!name || !type || !out || strlen(name) < 8 ||
        !((name[0] == 'v' || name[0] == 'f' || name[0] == 'c') &&
          name[1] == 'p' && !strncmp(name + 2, "_t_cb", 5))) return 0;
    const char *digits = name + 7;
    if (*digits < '0' || *digits > '9') return 0;
    char *end;
    unsigned long slots = strtoul(digits, &end, 10);
    if (slots > UINT32_MAX || *end != '_') return 0;
    const char *hex = end + 1;
    if (!((*hex >= '0' && *hex <= '9') || (*hex >= 'A' && *hex <= 'F'))) return 0;
    unsigned long handle = strtoul(hex, &end, 16);
    if (handle > UINT32_MAX) return 0;
    int sampler = strcmp(end, "Smplr") == 0;
    if (*end && !sampler) return 0;
    unsigned texture_bank = (unsigned)slots & 0xffffu;
    unsigned sampler_bank = (unsigned)slots >> 16;
    unsigned texture_byte = ((unsigned)handle & 0x3fffu) * 4u;
    unsigned sampler_byte = (((unsigned)handle >> 14) & 0x3fffu) * 4u;
    if (texture_bank < 3 || texture_bank > 16 || sampler_bank != 3 ||
        ((unsigned)handle >> 28) != 1 ||
        sampler_byte < 0x568 || sampler_byte >= 0x568 + 128 * 8 ||
        (sampler_byte - 0x568) % 8 ||
        strcmp(type, sampler ? "sampler" : "texture2d<float>")) return 0;
    *out = (nvn_indirect_single_texture){(uint16_t)(texture_bank - 3), (uint16_t)texture_byte,
                                         (uint16_t)((sampler_byte - 0x568) / 8), (uint8_t)sampler};
    return 1;
}

enum {
    NVN_INDIRECT_RANGE_DISJOINT,
    NVN_INDIRECT_RANGE_OVERLAP,
    NVN_INDIRECT_RANGE_UNKNOWN
};

/* Numeric guest ranges alone cannot detect distinct virtual mappings of the
   same physical storage; a disjoint result is only a diagnostic observation. */
static inline int nvn_indirect_range_relation(uint64_t a, uint64_t an, uint64_t aserial,
                                               uint64_t b, uint64_t bn, uint64_t bserial) {
    if (aserial && aserial == bserial) return NVN_INDIRECT_RANGE_OVERLAP;
    if (!a || !b || !an || !bn || an - 1 > UINT64_MAX - a || bn - 1 > UINT64_MAX - b)
        return NVN_INDIRECT_RANGE_UNKNOWN;
    return a <= b ? b - a < an ? NVN_INDIRECT_RANGE_OVERLAP : NVN_INDIRECT_RANGE_DISJOINT
                  : a - b < bn ? NVN_INDIRECT_RANGE_OVERLAP : NVN_INDIRECT_RANGE_DISJOINT;
}

/* The caller must supply a coherent snapshot from the replay timeline. */
static inline int nvn_indirect_texture_unpack(const void *snapshot, size_t size, unsigned count,
                                             uint32_t sampler_handle, nvn_indirect_texture_ids *out) {
    if (!snapshot || !out || !count || count > 32 || size < (count - 1) * 8u + 4u) return 0;
    const uint8_t *bytes = snapshot;
    for (unsigned i = 0; i < count; i++) {
        uint32_t handle;
        memcpy(&handle, bytes + 8u * i, sizeof handle);
        handle |= sampler_handle;
        out[i] = (nvn_indirect_texture_ids){handle & 0xfffffu, (handle >> 20) & 0xfffu};
    }
    return 1;
}

typedef int (*nvn_indirect_resolve_fn)(void *context, nvn_indirect_texture_ids ids,
                                       uint64_t *texture, uint64_t *sampler);
enum {
    NVN_INDIRECT_OK = 0,
    NVN_INDIRECT_INVALID,
    NVN_INDIRECT_RESOURCE_UNAVAILABLE,
    NVN_INDIRECT_SNAPSHOT_UNAVAILABLE
};

typedef struct {
    nvn_indirect_texture_ids ids;
    unsigned texture_slot, sampler_slot;
} nvn_indirect_scalar_binding;

/* The caller owns resource leases acquired by resolve, including on failure. */
static inline int nvn_indirect_scalar_bind_ids(const nvn_indirect_scalar_binding *bindings, unsigned count,
                                               uint64_t *slots, size_t slot_count,
                                               nvn_indirect_resolve_fn resolve, void *context,
                                               unsigned *failed_index) {
    uint64_t textures[64], samplers[64];
    if (!bindings || !slots || !resolve || !count || count > 64) return NVN_INDIRECT_INVALID;
    for (unsigned i = 0; i < count; i++) {
        unsigned t = bindings[i].texture_slot, s = bindings[i].sampler_slot;
        if (t >= slot_count || s >= slot_count || t == s) return NVN_INDIRECT_INVALID;
        for (unsigned j = 0; j < i; j++) {
            unsigned pt = bindings[j].texture_slot, ps = bindings[j].sampler_slot;
            if (t == pt || t == ps || s == pt || s == ps) return NVN_INDIRECT_INVALID;
        }
    }
    for (unsigned i = 0; i < count; i++) {
        if (!resolve(context, bindings[i].ids, &textures[i], &samplers[i]) || !textures[i] || !samplers[i]) {
            if (failed_index) *failed_index = i;
            return NVN_INDIRECT_RESOURCE_UNAVAILABLE;
        }
    }
    for (unsigned i = 0; i < count; i++) {
        slots[bindings[i].texture_slot] = textures[i];
        slots[bindings[i].sampler_slot] = samplers[i];
    }
    return NVN_INDIRECT_OK;
}

/* The resolver must validate resource type; the caller must arrange residency
   and dependencies. No slots are modified unless the whole array resolves. */
static inline int nvn_indirect_texture_bind_ids(const nvn_indirect_texture_ids *ids, unsigned count,
                                                uint64_t *slots, size_t slot_count,
                                                unsigned texture_start, unsigned sampler_start,
                                                nvn_indirect_resolve_fn resolve, void *context,
                                                unsigned *failed_index) {
    uint64_t textures[32], samplers[32];
    if (!ids || !slots || !resolve || !count || count > 32 ||
        texture_start > slot_count || count > slot_count - texture_start ||
        sampler_start > slot_count || count > slot_count - sampler_start ||
        ((size_t)texture_start < (size_t)sampler_start + count &&
         (size_t)sampler_start < (size_t)texture_start + count))
        return NVN_INDIRECT_INVALID;
    for (unsigned i = 0; i < count; i++) {
        if (!resolve(context, ids[i], &textures[i], &samplers[i]) || !textures[i] || !samplers[i]) {
            if (failed_index) *failed_index = i;
            return NVN_INDIRECT_RESOURCE_UNAVAILABLE;
        }
    }
    memcpy(slots + texture_start, textures, count * sizeof *textures);
    memcpy(slots + sampler_start, samplers, count * sizeof *samplers);
    return NVN_INDIRECT_OK;
}

static inline int nvn_indirect_texture_bind(const void *snapshot, size_t size, unsigned count,
                                             uint32_t sampler_handle, uint64_t *slots, size_t slot_count,
                                             unsigned texture_start, unsigned sampler_start,
                                             nvn_indirect_resolve_fn resolve, void *context,
                                             unsigned *failed_index) {
    nvn_indirect_texture_ids ids[32];
    if (!nvn_indirect_texture_unpack(snapshot, size, count, sampler_handle, ids))
        return NVN_INDIRECT_INVALID;
    return nvn_indirect_texture_bind_ids(ids, count, slots, slot_count, texture_start,
                                          sampler_start, resolve, context, failed_index);
}

static inline int nvn_indirect_texture_decode_form(const char *name, const char *type,
                                                   const char *name_part, const char *texture_part,
                                                   nvn_indirect_texture *out) {
    if (!name || !type || !out) return 0;
    size_t part_len = strlen(name_part);
    if (strlen(name) < 3 + part_len) return 0;
    if (!((name[0] == 'v' || name[0] == 'f' || name[0] == 'c') &&
          name[1] == 'p' && !strncmp(name + 2, name_part, part_len))) return 0;
    const char *digits = name + 2 + part_len;
    if (*digits < '0' || *digits > '9') return 0;
    char *end;
    unsigned long slots = strtoul(digits, &end, 10);
    if (slots > UINT32_MAX || *end != '_') return 0;
    const char *hex = end + 1;
    if (!((*hex >= '0' && *hex <= '9') || (*hex >= 'A' && *hex <= 'F'))) return 0;
    unsigned long handle = strtoul(hex, &end, 16);
    if (handle > UINT32_MAX) return 0;
    int sampler = strcmp(end, "Smplr") == 0;
    if (*end && !sampler) return 0;
    unsigned texture_bank = (unsigned)slots & 0xffffu;
    unsigned sampler_bank = (unsigned)slots >> 16;
    unsigned offset = ((unsigned)handle >> 14) & 0x3fffu;
    unsigned sampler_byte = offset * 4u;
    if (texture_bank < 3 || texture_bank > 16 || sampler_bank != 3 ||
        ((unsigned)handle >> 28) != 1 || ((unsigned)handle & 0x3fffu) != 0 ||
        sampler_byte < 0x568 || sampler_byte >= 0x568 + 128 * 8 ||
        (sampler_byte - 0x568) % 8) return 0;

    const char *prefix = sampler ? "array<sampler, " : texture_part;
    if (strncmp(type, prefix, strlen(prefix))) return 0;
    const char *count_start = type + strlen(prefix);
    if (*count_start < '0' || *count_start > '9') return 0;
    unsigned long count = strtoul(count_start, &end, 10);
    if (!count || count > 32 || strcmp(end, ">")) return 0;
    *out = (nvn_indirect_texture){(uint16_t)(texture_bank - 3),
                                  (uint16_t)((sampler_byte - 0x568) / 8),
                                  (uint16_t)count, (uint8_t)sampler};
    return 1;
}
static inline int nvn_indirect_texture_decode(const char *name, const char *type,
                                              nvn_indirect_texture *out) {
    return nvn_indirect_texture_decode_form(name, type, "_t3d_cb", "array<texture3d<float>, ", out);
}
static inline int nvn_indirect_cube_decode(const char *name, const char *type,
                                           nvn_indirect_texture *out) {
    return nvn_indirect_texture_decode_form(name, type, "_tcube_cb", "array<texturecube<float>, ", out);
}
static inline int nvn_indirect_2d_decode(const char *name, const char *type,
                                         nvn_indirect_texture *out) {
    return nvn_indirect_texture_decode_form(name, type, "_t2d_cb", "array<texture2d<float>, ", out);
}
