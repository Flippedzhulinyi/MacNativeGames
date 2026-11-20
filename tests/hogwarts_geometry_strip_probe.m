#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "geometry_strip.h"
#include <stdio.h>
#include <string.h>

int main(void) {
    @autoreleasepool {
        uint32_t map[9] = {0};
        const uint32_t expected[] = {0, 1, 2, 2, 1, 3, 2, 3, 4};
        size_t written = 77;
        if (hogwarts_geometry_strip_remap(5, 1, map, 9, &written) || written != 77 ||
            hogwarts_geometry_strip_remap(5, 0, map, 8, &written) || written != 77 ||
            hogwarts_geometry_strip_remap(2, 0, map, 9, &written) || written != 77 ||
            hogwarts_geometry_strip_remap(UINT32_MAX, 0, map, 9, &written) || written != 77 ||
            hogwarts_geometry_strip_remap(5, 0, NULL, 9, &written) ||
            hogwarts_geometry_strip_remap(5, 0, map, 9, NULL)) return 1;
        for (size_t i = 0; i < 9; i++) if (map[i]) return 2;
        if (!hogwarts_geometry_strip_remap(5, 0, map, 9, &written) ||
            written != 9 || memcmp(map, expected, sizeof map)) return 3;
        uint32_t first[3];
        if (!hogwarts_geometry_strip_remap(3, 0, first, 3, &written) ||
            written != 3 || memcmp(first, expected, sizeof first)) return 4;

        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) { fprintf(stderr, "no Metal device\n"); return 5; }
        NSString *source = @"#include <metal_stdlib>\n"
            "using namespace metal;\n"
            "kernel void remap(device const uint *map [[buffer(0)]], "
            "device uint *result [[buffer(1)]], constant uint &n [[buffer(2)]], "
            "uint2 id [[thread_position_in_grid]]) {"
            "if (id.x < n && id.y < 32) result[id.y * n + id.x] = id.y * 100 + map[id.x];"
            "}";
        NSError *error = nil;
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        if (!library) { fprintf(stderr, "Metal compile: %s\n", error.localizedDescription.UTF8String); return 6; }
        id<MTLFunction> function = [library newFunctionWithName:@"remap"];
        id<MTLComputePipelineState> pipeline = [device newComputePipelineStateWithFunction:function error:&error];
        if (!pipeline) { fprintf(stderr, "Metal pipeline: %s\n", error.localizedDescription.UTF8String); return 7; }
        id<MTLBuffer> input = [device newBufferWithBytes:map length:sizeof map options:MTLResourceStorageModeShared];
        id<MTLBuffer> result = [device newBufferWithLength:32 * 9 * sizeof(uint32_t) options:MTLResourceStorageModeShared];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!input || !result || !queue) {
            fprintf(stderr, "Metal resource allocation failed\n"); return 8;
        }
        int negative = getenv("HOGWARTS_STRIP_PROBE_BAD_EXPECTED") != NULL;
        for (unsigned pass = 0; pass < 2; pass++) {
            uint32_t n = pass ? 9 : 3;
            id<MTLCommandBuffer> command = [queue commandBuffer];
            id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
            if (!command || !encoder) { fprintf(stderr, "Metal encoder creation failed\n"); return 8; }
            memset(result.contents, 0xff, result.length);
            [encoder setComputePipelineState:pipeline];
            [encoder setBuffer:input offset:0 atIndex:0];
            [encoder setBuffer:result offset:0 atIndex:1];
            [encoder setBytes:&n length:sizeof n atIndex:2];
            [encoder dispatchThreads:MTLSizeMake(n, 32, 1) threadsPerThreadgroup:MTLSizeMake(n, 1, 1)];
            [encoder endEncoding];
            [command commit];
            [command waitUntilCompleted];
            if (command.status != MTLCommandBufferStatusCompleted) {
                fprintf(stderr, "Metal execution: %s\n", command.error.localizedDescription.UTF8String ?: "incomplete"); return 9;
            }
            uint32_t *actual = result.contents;
            for (unsigned instance = 0; instance < 32; instance++) {
                for (unsigned i = 0; i < n; i++) {
                    uint32_t want = instance * 100 + expected[i] + (negative && pass && instance == 31 && i == 8);
                    if (actual[instance * n + i] != want) {
                        fprintf(stderr, "strip readback mismatch instance=%u element=%u\n", instance, i);
                        return 10;
                    }
                }
            }
        }
    }
    return 0;
}
