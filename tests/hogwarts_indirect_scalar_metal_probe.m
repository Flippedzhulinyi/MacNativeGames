#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "nvn_indirect_texture.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint64_t textures[3], sampler;
} scalar_resources;

static int resolve_scalar(void *context, nvn_indirect_texture_ids ids, uint64_t *texture, uint64_t *sampler) {
    const scalar_resources *resources = context;
    if (ids.texture_id < 1 || ids.texture_id > 2 || ids.sampler_id != 1) return 0;
    *texture = resources->textures[ids.texture_id];
    *sampler = resources->sampler;
    return 1;
}

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) { fprintf(stderr, "Metal device unavailable\n"); return 1; }
        NSString *source = @"#include <metal_stdlib>\nusing namespace metal;\n"
            "struct Args { texture2d<float> t0 [[id(0)]]; sampler s0 [[id(1)]]; "
            "texture2d<float> t1 [[id(2)]]; sampler s1 [[id(3)]]; }; "
            "kernel void test(constant Args& a [[buffer(0)]], device float *out [[buffer(1)]]) { "
            "out[0] = a.t0.sample(a.s0, float2(0.5)).x; "
            "out[1] = a.t1.sample(a.s1, float2(0.5)).x; }";
        NSError *error = nil;
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        id<MTLFunction> function = [library newFunctionWithName:@"test"];
        id<MTLComputePipelineState> pipeline = function ?
            [device newComputePipelineStateWithFunction:function error:&error] : nil;
        id<MTLArgumentEncoder> encoder = [function newArgumentEncoderWithBufferIndex:0];
        if (!pipeline || !encoder || encoder.encodedLength != 4 * sizeof(uint64_t)) {
            fprintf(stderr, "scalar shader or layout unavailable: %s\n",
                    error.localizedDescription.UTF8String ?: "layout mismatch");
            return 2;
        }
        MTLTextureDescriptor *desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatR32Float
                                                                                        width:1 height:1 mipmapped:NO];
        desc.storageMode = MTLStorageModeShared; desc.usage = MTLTextureUsageShaderRead;
        id<MTLTexture> textures[2] = {[device newTextureWithDescriptor:desc], [device newTextureWithDescriptor:desc]};
        MTLSamplerDescriptor *sampler_desc = [MTLSamplerDescriptor new];
        sampler_desc.supportArgumentBuffers = YES;
        id<MTLSamplerState> sampler = [device newSamplerStateWithDescriptor:sampler_desc];
        id<MTLBuffer> arguments = [device newBufferWithLength:encoder.encodedLength options:MTLResourceStorageModeShared];
        id<MTLBuffer> expected_layout = [device newBufferWithLength:encoder.encodedLength options:MTLResourceStorageModeShared];
        id<MTLBuffer> output = [device newBufferWithLength:2 * sizeof(float) options:MTLResourceStorageModeShared];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!textures[0] || !textures[1] || !sampler || !arguments || !expected_layout || !output || !queue) {
            fprintf(stderr, "scalar resources unavailable\n"); return 3;
        }
        for (int i = 0; i < 2; i++) {
            float value = i ? .75f : .25f;
            [textures[i] replaceRegion:MTLRegionMake2D(0, 0, 1, 1) mipmapLevel:0 withBytes:&value bytesPerRow:4];
        }
        scalar_resources resources = {{0, textures[0].gpuResourceID._impl, textures[1].gpuResourceID._impl},
                                      sampler.gpuResourceID._impl};
        for (int pass = 0; pass < 2; pass++) {
            uint32_t handles[2] = {pass ? 2u : 1u, pass ? 1u : 2u};
            nvn_indirect_texture_ids ids[2];
            nvn_indirect_scalar_binding bindings[2];
            for (int i = 0; i < 2; i++) {
                if (!nvn_indirect_texture_unpack(&handles[i], sizeof handles[i], 1, 1u << 20, &ids[i])) {
                    fprintf(stderr, "scalar handle resolution failed\n"); return 4;
                }
                bindings[i] = (nvn_indirect_scalar_binding){ids[i], (unsigned)i * 2, (unsigned)i * 2 + 1};
            }
            if (nvn_indirect_scalar_bind_ids(bindings, 2, arguments.contents, 4,
                                             resolve_scalar, &resources, NULL) != NVN_INDIRECT_OK) {
                fprintf(stderr, "scalar handle resolution failed\n"); return 4;
            }
            [encoder setArgumentBuffer:expected_layout offset:0];
            for (int i = 0; i < 2; i++) {
                [encoder setTexture:textures[handles[i] - 1] atIndex:(NSUInteger)(i * 2)];
                [encoder setSamplerState:sampler atIndex:(NSUInteger)(i * 2 + 1)];
            }
            if (memcmp(arguments.contents, expected_layout.contents, encoder.encodedLength)) {
                fprintf(stderr, "scalar argument buffer mismatch\n"); return 5;
            }
            id<MTLCommandBuffer> commands = [queue commandBuffer];
            id<MTLComputeCommandEncoder> compute = [commands computeCommandEncoder];
            [compute setComputePipelineState:pipeline];
            [compute setBuffer:arguments offset:0 atIndex:0];
            [compute setBuffer:output offset:0 atIndex:1];
            for (int i = 0; i < 2; i++) [compute useResource:textures[i] usage:MTLResourceUsageRead];
            [compute dispatchThreads:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
            [compute endEncoding];
            [commands commit]; [commands waitUntilCompleted];
            if (commands.status != MTLCommandBufferStatusCompleted) {
                fprintf(stderr, "scalar GPU execution failed: %s\n", commands.error.localizedDescription.UTF8String);
                return 6;
            }
            const float *got = output.contents;
            float expected0 = pass ? .75f : .25f, expected1 = pass ? .25f : .75f;
            if (getenv("HOGWARTS_SCALAR_PROBE_BAD_EXPECTED")) expected0 += 1.f;
            if (fabsf(got[0] - expected0) > .0001f || fabsf(got[1] - expected1) > .0001f) {
                fprintf(stderr, "scalar GPU result mismatch: %.3f %.3f expected %.3f %.3f\n",
                        got[0], got[1], expected0, expected1);
                return 7;
            }
        }
        return 0;
    }
}
