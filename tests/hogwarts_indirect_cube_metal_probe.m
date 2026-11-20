#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "nvn_indirect_texture.h"
#include <math.h>
#include <stdio.h>

typedef struct { uint64_t textures[33], sampler; } cube_resources;
static int resolve_cube(void *context, nvn_indirect_texture_ids ids, uint64_t *texture, uint64_t *sampler) {
    cube_resources *resources = context;
    if (!ids.texture_id || ids.texture_id > 32 || ids.sampler_id != 1) return 0;
    *texture = resources->textures[ids.texture_id];
    *sampler = resources->sampler;
    return 1;
}

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) { fprintf(stderr, "Metal device unavailable\n"); return 1; }
        BOOL array2d = getenv("HOGWARTS_PROBE_2D_ARRAY") != NULL;
        NSString *source = array2d ? @"#include <metal_stdlib>\nusing namespace metal;\n"
            "struct Args { array<texture2d<float>,32> textures [[id(0)]]; "
            "array<sampler,32> samplers [[id(32)]]; }; "
            "kernel void test(constant Args& a [[buffer(0)]], device const uint *idx [[buffer(1)]], "
            "device float *out [[buffer(2)]], uint tid [[thread_position_in_grid]]) { "
            "uint i=idx[tid]; out[tid]=a.textures[i].sample(a.samplers[i],float2(0.5)).x; }" :
            @"#include <metal_stdlib>\nusing namespace metal;\n"
            "struct Args { array<texturecube<float>,32> textures [[id(0)]]; "
            "array<sampler,32> samplers [[id(32)]]; }; "
            "kernel void test(constant Args& a [[buffer(0)]], device const uint *idx [[buffer(1)]], "
            "device float *out [[buffer(2)]], uint tid [[thread_position_in_grid]]) { "
            "uint i=idx[tid]; out[tid]=a.textures[i].sample(a.samplers[i],float3(1,0,0)).x; }";
        NSError *error = nil;
        id<MTLLibrary> lib = [device newLibraryWithSource:source options:nil error:&error];
        id<MTLFunction> fn = [lib newFunctionWithName:@"test"];
        id<MTLComputePipelineState> pipeline = fn ? [device newComputePipelineStateWithFunction:fn error:&error] : nil;
        id<MTLArgumentEncoder> encoder = [fn newArgumentEncoderWithBufferIndex:0];
        if (!pipeline || !encoder || encoder.encodedLength != 64 * sizeof(uint64_t)) {
            fprintf(stderr, "array shader or layout unavailable: %s\n", error.localizedDescription.UTF8String ?: "layout");
            return 2;
        }
        MTLTextureDescriptor *desc = array2d ?
            [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatR32Float width:1 height:1 mipmapped:NO] :
            [MTLTextureDescriptor textureCubeDescriptorWithPixelFormat:MTLPixelFormatR32Float size:1 mipmapped:NO];
        desc.storageMode = MTLStorageModeShared; desc.usage = MTLTextureUsageShaderRead;
        NSMutableArray<id<MTLTexture>> *textures = [NSMutableArray array];
        cube_resources resources = {0};
        for (int i = 0; i < 32; i++) {
            id<MTLTexture> tex = [device newTextureWithDescriptor:desc];
            if (!tex) { fprintf(stderr, "array texture allocation failed\n"); return 3; }
            float value = (float)(i + 1);
            for (int face = 0; face < (array2d ? 1 : 6); face++)
                [tex replaceRegion:MTLRegionMake2D(0,0,1,1) mipmapLevel:0 slice:(NSUInteger)face
                         withBytes:&value bytesPerRow:sizeof value bytesPerImage:sizeof value];
            [textures addObject:tex];
            resources.textures[i + 1] = tex.gpuResourceID._impl;
        }
        MTLSamplerDescriptor *sd = [MTLSamplerDescriptor new]; sd.supportArgumentBuffers = YES;
        id<MTLSamplerState> sampler = [device newSamplerStateWithDescriptor:sd];
        id<MTLBuffer> args = [device newBufferWithLength:encoder.encodedLength options:MTLResourceStorageModeShared];
        id<MTLBuffer> reference = [device newBufferWithLength:encoder.encodedLength options:MTLResourceStorageModeShared];
        uint32_t indices[] = {0, 7, 31};
        id<MTLBuffer> index = [device newBufferWithBytes:indices length:sizeof indices options:MTLResourceStorageModeShared];
        id<MTLBuffer> output = [device newBufferWithLength:sizeof(float) * 3 options:MTLResourceStorageModeShared];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!sampler || !args || !reference || !index || !output || !queue) {
            fprintf(stderr, "array resources unavailable\n"); return 4;
        }
        resources.sampler = sampler.gpuResourceID._impl;
        for (int pass = 0; pass < 2; pass++) {
            uint64_t handles[32];
            [encoder setArgumentBuffer:reference offset:0];
            for (int i = 0; i < 32; i++) {
                unsigned t = ((unsigned)i + (unsigned)pass) % 32;
                handles[i] = t + 1;
                [encoder setTexture:textures[t] atIndex:(NSUInteger)i];
                [encoder setSamplerState:sampler atIndex:(NSUInteger)i + 32];
            }
            if (nvn_indirect_texture_bind(handles, sizeof handles, 32, 1u << 20, args.contents, 64, 0, 32,
                                          resolve_cube, &resources, NULL) != NVN_INDIRECT_OK ||
                memcmp(args.contents, reference.contents, encoder.encodedLength)) {
                fprintf(stderr, "array argument layout mismatch\n"); return 5;
            }
            id<MTLCommandBuffer> commands = [queue commandBuffer];
            id<MTLComputeCommandEncoder> compute = [commands computeCommandEncoder];
            [compute setComputePipelineState:pipeline];
            [compute setBuffer:args offset:0 atIndex:0]; [compute setBuffer:index offset:0 atIndex:1];
            [compute setBuffer:output offset:0 atIndex:2];
            for (id<MTLTexture> tex in textures) [compute useResource:tex usage:MTLResourceUsageRead];
            [compute dispatchThreads:MTLSizeMake(3,1,1) threadsPerThreadgroup:MTLSizeMake(3,1,1)];
            [compute endEncoding]; [commands commit]; [commands waitUntilCompleted];
            if (commands.status != MTLCommandBufferStatusCompleted) {
                fprintf(stderr, "array GPU execution failed: %s\n", commands.error.localizedDescription.UTF8String);
                return 6;
            }
            float *got = output.contents;
            for (int i = 0; i < 3; i++) {
                float expected = (float)((indices[i] + (unsigned)pass) % 32 + 1);
                if ((getenv("HOGWARTS_CUBE_PROBE_BAD_EXPECTED") ||
                     getenv("HOGWARTS_2D_ARRAY_PROBE_BAD_EXPECTED")) && i == 0) expected += 1;
                if (fabsf(got[i] - expected) > .0001f) {
                    fprintf(stderr, "array GPU result mismatch: %.3f expected %.3f\n", got[i], expected);
                    return 7;
                }
            }
        }
        return 0;
    }
}
