#pragma once
#include <stddef.h>
#include <stdint.h>

/* Remap non-indexed triangle-strip vertex ordinals to consistently wound
   triangle-list ordinals. Indexed draws and restart need a separate path. */
static inline int hogwarts_geometry_strip_remap(uint32_t vertex_count, int indexed,
                                                uint32_t *out, size_t capacity,
                                                size_t *written) {
    if (!written || indexed || vertex_count < 3) return 0;
    size_t triangles = (size_t)vertex_count - 2;
    if (triangles > SIZE_MAX / 3) return 0;
    size_t count = triangles * 3;
    if (!out || capacity < count) return 0;
    for (size_t i = 0; i < triangles; i++) {
        out[3 * i] = (uint32_t)(i + (i & 1));
        out[3 * i + 1] = (uint32_t)(i + !(i & 1));
        out[3 * i + 2] = (uint32_t)(i + 2);
    }
    *written = count;
    return 1;
}
