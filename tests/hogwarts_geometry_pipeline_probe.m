#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "geometry_strip.h"
#include "geometry_layout.h"
#include <stdio.h>
#include <string.h>

enum { VERTICES = 5, INSTANCES = 32, INPUT_WORDS = 13, OUTPUT_WORDS = 14, MAX_OUTPUT = 3 };

int main(void) {
    @autoreleasepool {
        uint32_t remap[9]; size_t count = 0;
        if (!hogwarts_geometry_strip_remap(VERTICES, 0, remap, 9, &count) || count != 9) return 1;
        hogwarts_geometry_layout layout = {1, 2, 3};
        if (hogwarts_geometry_layout_single(3, 1, 32, 2, 3, 13, 14, SIZE_MAX, &layout) ||
            hogwarts_geometry_layout_single(UINT32_MAX, 1, 32, 1, 3, 13, 14, SIZE_MAX, &layout) ||
            hogwarts_geometry_layout_single(3, 4, 32, 1, 3, 13, 14, SIZE_MAX, &layout) ||
            hogwarts_geometry_layout_single(3, 1, 32, 1, 3, 13, 14, 100, &layout) ||
            hogwarts_geometry_layout_single(3, 1, 32, 1, 3, 13, 14, 22655, &layout) ||
            hogwarts_geometry_layout_single(3, 1, 32, 1, 0, 13, 14, SIZE_MAX, &layout) ||
            layout.vertex_bytes != 1 || layout.geometry_bytes != 2 || layout.index_bytes != 3 ||
            hogwarts_geometry_layout_single(3, 1, 32, 1, 3, 13, 14, SIZE_MAX, NULL) ||
            !hogwarts_geometry_layout_single(3, 1, 32, 1, 3, 13, 14, 22656, &layout) ||
            layout.vertex_bytes != 4992 || layout.geometry_bytes != 16128 || layout.index_bytes != 1536 ||
            !hogwarts_geometry_layout_single(VERTICES, 3, INSTANCES, 1, MAX_OUTPUT, INPUT_WORDS,
                                             OUTPUT_WORDS, SIZE_MAX, &layout)) {
            fprintf(stderr, "geometry layout validation failed\n"); return 16;
        }
        const uint32_t expected[9] = {0, 1, 2, 2, 1, 3, 2, 3, 4};
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) { fprintf(stderr, "no Metal device\n"); return 2; }
        NSString *source = @"#include <metal_stdlib>\n"
            "using namespace metal;\n"
            "kernel void vs(device uint *out [[buffer(0)]], uint2 id [[thread_position_in_grid]]) {"
            "if (id.x >= 5 || id.y >= 32) return;"
            "for (uint w=0; w<13; w++) out[(id.y*5+id.x)*13+w]=id.y*10000+id.x*100+w;"
            "}\n"
            "kernel void gs(device const uint *in [[buffer(0)]], device const uint *map [[buffer(1)]],"
            "device uint *out [[buffer(2)]], device uint *idx [[buffer(3)]],"
            "uint2 id [[thread_position_in_grid]]) {"
            "if (id.x >= 3 || id.y >= 32) return;"
            "uint base=(id.y*5+id.x)*3;"
            "for (uint v=0; v<3; v++) {"
            "uint src=(id.y*5+map[id.x*3+v])*13;"
            "for (uint w=0; w<13; w++) out[(base+v)*14+w]=in[src+w];"
            "out[(base+v)*14+13]=id.x*10+v; idx[(id.y*5+id.x)*4+v]=base+v;"
            "}"
            "}";
        NSError *error = nil;
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        if (!library) { fprintf(stderr, "Metal compile: %s\n", error.localizedDescription.UTF8String); return 3; }
        id<MTLFunction> vs = [library newFunctionWithName:@"vs"], gs = [library newFunctionWithName:@"gs"];
        if (!vs || !gs) { fprintf(stderr, "missing compute entry\n"); return 4; }
        id<MTLComputePipelineState> vp = [device newComputePipelineStateWithFunction:vs error:&error];
        if (!vp) { fprintf(stderr, "vertex pipeline: %s\n", error.localizedDescription.UTF8String); return 5; }
        id<MTLComputePipelineState> gp = [device newComputePipelineStateWithFunction:gs error:&error];
        if (!gp) { fprintf(stderr, "geometry pipeline: %s\n", error.localizedDescription.UTF8String); return 6; }
        size_t out_words = layout.geometry_bytes / 4, index_words = layout.index_bytes / 4;
        id<MTLBuffer> input = [device newBufferWithLength:layout.vertex_bytes options:MTLResourceStorageModeShared];
        id<MTLBuffer> map = [device newBufferWithBytes:remap length:sizeof remap options:MTLResourceStorageModeShared];
        id<MTLBuffer> output = [device newBufferWithLength:(out_words + 16) * 4 options:MTLResourceStorageModeShared];
        id<MTLBuffer> indices = [device newBufferWithLength:(index_words + 16) * 4 options:MTLResourceStorageModeShared];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!input || !map || !output || !indices || !queue) { fprintf(stderr, "Metal allocation failed\n"); return 7; }
        memset(input.contents, 0xff, input.length);
        memset(output.contents, 0xff, output.length);
        memset(indices.contents, 0xff, indices.length);
        id<MTLCommandBuffer> cb = [queue commandBuffer];
        id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
        if (!cb || !ce) { fprintf(stderr, "vertex encoder failed\n"); return 8; }
        [ce setComputePipelineState:vp]; [ce setBuffer:input offset:0 atIndex:0];
        [ce dispatchThreads:MTLSizeMake(VERTICES, INSTANCES, 1) threadsPerThreadgroup:MTLSizeMake(5, 1, 1)];
        [ce endEncoding];
        ce = [cb computeCommandEncoder];
        if (!ce) { fprintf(stderr, "geometry encoder failed\n"); return 9; }
        [ce setComputePipelineState:gp];
        [ce setBuffer:input offset:0 atIndex:0]; [ce setBuffer:map offset:0 atIndex:1];
        [ce setBuffer:output offset:0 atIndex:2]; [ce setBuffer:indices offset:0 atIndex:3];
        [ce dispatchThreads:MTLSizeMake(3, INSTANCES, 1) threadsPerThreadgroup:MTLSizeMake(3, 1, 1)];
        [ce endEncoding]; [cb commit]; [cb waitUntilCompleted];
        if (cb.status != MTLCommandBufferStatusCompleted) {
            fprintf(stderr, "Metal execution: %s\n", cb.error.localizedDescription.UTF8String ?: "incomplete"); return 10;
        }
        const uint32_t *actual = output.contents, *actual_indices = indices.contents, *vs_result = input.contents;
        int negative = getenv("HOGWARTS_PIPELINE_PROBE_BAD_EXPECTED") != NULL;
        for (unsigned inst = 0; inst < INSTANCES; inst++) {
            for (unsigned v = 0; v < VERTICES; v++)
                for (unsigned w = 0; w < INPUT_WORDS; w++)
                    if (vs_result[(inst * VERTICES + v) * INPUT_WORDS + w] != inst * 10000 + v * 100 + w) {
                        fprintf(stderr, "vertex readback mismatch\n"); return 11;
                    }
            for (unsigned p = 0; p < VERTICES; p++) {
                unsigned base = (inst * VERTICES + p) * MAX_OUTPUT;
                for (unsigned v = 0; v < MAX_OUTPUT; v++) {
                    unsigned index = (inst * VERTICES + p) * (MAX_OUTPUT + 1) + v;
                    if (actual_indices[index] != (p < 3 ? base + v : UINT32_MAX)) {
                        fprintf(stderr, "index readback mismatch\n"); return 12;
                    }
                    for (unsigned w = 0; w < OUTPUT_WORDS; w++) {
                        uint32_t want = p >= 3 ? UINT32_MAX : w == 13 ? p * 10 + v :
                            inst * 10000 + expected[p * 3 + v] * 100 + w;
                        if (negative && inst == 31 && p == 2 && v == 2 && w == 12) want++;
                        if (actual[(base + v) * OUTPUT_WORDS + w] != want) {
                            fprintf(stderr, "geometry readback mismatch instance=%u primitive=%u vertex=%u word=%u\n", inst, p, v, w); return 13;
                        }
                    }
                }
                if (actual_indices[(inst * VERTICES + p) * (MAX_OUTPUT + 1) + 3] != UINT32_MAX) {
                    fprintf(stderr, "restart slot overwritten\n"); return 14;
                }
            }
        }
        for (unsigned i = 0; i < 16; i++)
            if (actual[out_words + i] != UINT32_MAX || actual_indices[index_words + i] != UINT32_MAX) {
                fprintf(stderr, "geometry output guard overwritten\n"); return 15;
            }
    }
    return 0;
}
