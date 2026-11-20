#pragma once
#include "nvn_indirect_texture.h"
#include "nvn_obj.h"

/* Numeric guest ranges cannot prove physical disjointness, even for pools
   without the NVN virtual flag: their host mappings may still alias. */
static inline int nvn_indirect_texture_relation(const tex_t *sampled, const tex_t *target) {
    if (!sampled || !target) return NVN_INDIRECT_RANGE_UNKNOWN;
    int relation = nvn_indirect_range_relation((uint64_t)(uintptr_t)sampled->mem, sampled->L.size, sampled->serial,
                                                (uint64_t)(uintptr_t)target->mem, target->L.size, target->serial);
    if (relation == NVN_INDIRECT_RANGE_OVERLAP) return relation;
    return NVN_INDIRECT_RANGE_UNKNOWN;
}
