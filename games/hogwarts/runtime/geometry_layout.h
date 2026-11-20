#pragma once
#include <limits.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    size_t vertex_bytes, geometry_bytes, index_bytes;
} hogwarts_geometry_layout;

/* Translated geometry indexing uses vertex_count as the per-instance stride.
   Multiple GS invocations are rejected until their indexing is validated. */
static inline int hogwarts_geometry_layout_single(uint32_t vertex_count, uint32_t primitive_count,
                                                  uint32_t instances, uint32_t invocations,
                                                  uint32_t max_output, uint32_t vertex_words,
                                                  uint32_t geometry_words, size_t byte_limit,
                                                  hogwarts_geometry_layout *out) {
    if (!out || !vertex_count || !primitive_count || primitive_count > vertex_count ||
        !instances || invocations != 1 || !max_output || !vertex_words || !geometry_words)
        return 0;
    uint64_t vertices = (uint64_t)vertex_count * instances;
    if (vertices > INT32_MAX || max_output > INT32_MAX / vertices ||
        (uint64_t)max_output + 1 > INT32_MAX / vertices) return 0;
    uint64_t emitted = vertices * max_output;
    uint64_t indices = vertices * ((uint64_t)max_output + 1);
    if (vertex_words > INT32_MAX / vertices || geometry_words > INT32_MAX / emitted) return 0;
    uint64_t vb = vertices * vertex_words * 4;
    uint64_t gb = emitted * geometry_words * 4;
    uint64_t ib = indices * 4;
    if (vb > SIZE_MAX || gb > SIZE_MAX || ib > SIZE_MAX ||
        vb > byte_limit || gb > byte_limit - vb || ib > byte_limit - vb - gb) return 0;
    *out = (hogwarts_geometry_layout){(size_t)vb, (size_t)gb, (size_t)ib};
    return 1;
}
