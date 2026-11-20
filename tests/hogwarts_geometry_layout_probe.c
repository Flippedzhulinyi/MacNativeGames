#include "geometry_layout.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    if (argc != 8) { fprintf(stderr, "expected seven numeric geometry parameters\n"); return 1; }
    uint32_t values[7];
    for (int i = 0; i < 7; i++) {
        char *end = NULL;
        errno = 0;
        unsigned long long value = strtoull(argv[i + 1], &end, 10);
        if (errno || !*argv[i + 1] || !end || *end || value > UINT32_MAX || argv[i + 1][0] == '-') {
            fprintf(stderr, "invalid geometry parameter\n"); return 2;
        }
        values[i] = (uint32_t)value;
    }
    hogwarts_geometry_layout layout;
    if (!hogwarts_geometry_layout_single(values[0], values[1], values[2], values[3],
                                        values[4], values[5], values[6], SIZE_MAX, &layout)) {
        fprintf(stderr, "unsafe or unsupported geometry layout\n"); return 3;
    }
    printf("%zu %zu %zu\n", layout.vertex_bytes, layout.geometry_bytes, layout.index_bytes);
    return 0;
}
