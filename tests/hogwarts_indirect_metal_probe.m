#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <CommonCrypto/CommonDigest.h>
#include "nvn_indirect_texture.h"
#include "nvn_refl.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    uint64_t textures[33], sampler;
} probe_resources;
static int resolve_resource(void *context, nvn_indirect_texture_ids ids, uint64_t *texture, uint64_t *sampler) {
    probe_resources *resources = context;
    if (ids.texture_id < 1 || ids.texture_id > 32 || ids.sampler_id != 1) return 0;
    *texture = resources->textures[ids.texture_id];
    *sampler = resources->sampler;
    return 1;
}

static int check_results(const float *actual, const float *expected, size_t count) {
    for (size_t i = 0; i < count; i++)
        if (fabsf(actual[i] - expected[i]) > 0.0001f) return 0;
    return 1;
}

static int run_local_fragment(id<MTLDevice> device, id<MTLFunction> fragment, id<MTLArgumentEncoder> encoder,
                              NSArray<id<MTLTexture>> *textures, id<MTLSamplerState> sampler, id<MTLTexture> depth,
                              id<MTLTexture> tex2d, id<MTLTexture> buf0, id<MTLTexture> buf1, id<MTLBuffer> typed) {
    NSError *error = nil;
    NSString *vertex_source = @"#include <metal_stdlib>\nusing namespace metal;\n"
                               "vertex float4 probe_vertex(uint i [[vertex_id]]) { "
                               "float2 p[] = {float2(-1,-1), float2(3,-1), float2(-1,3)}; "
                               "return float4(p[i], 0, 1); }";
    id<MTLLibrary> vertex_library = [device newLibraryWithSource:vertex_source options:nil error:&error];
    id<MTLFunction> vertex = [vertex_library newFunctionWithName:@"probe_vertex"];
    MTLRenderPipelineDescriptor *pipeline_desc = [MTLRenderPipelineDescriptor new];
    pipeline_desc.vertexFunction = vertex;
    pipeline_desc.fragmentFunction = fragment;
    pipeline_desc.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA32Float;
    id<MTLRenderPipelineState> pipeline =
        vertex ? [device newRenderPipelineStateWithDescriptor:pipeline_desc error:&error] : nil;
    if (!pipeline) {
        fprintf(stderr, "local fragment pipeline: %s\n", error.localizedDescription.UTF8String ?: "missing vertex");
        return 20;
    }
    NSMutableArray<id<MTLBuffer>> *buffers = [NSMutableArray array];
    for (int i = 0; i < 6; i++) {
        id<MTLBuffer> buffer = [device newBufferWithLength:65536 options:MTLResourceStorageModeShared];
        if (!buffer) {
            fprintf(stderr, "local fragment buffer allocation failed\n");
            return 21;
        }
        memset(buffer.contents, 0, buffer.length);
        [buffers addObject:buffer];
    }
    ((float *)buffers[0].contents)[192 / sizeof(float)] = 1.f;
    ((float *)buffers[2].contents)[70 * 4 + 2] = 1.f;
    ((float *)buffers[3].contents)[4 * 4 + 1] = 1.f;
    ((uint32_t *)buffers[3].contents)[2 * 4 + 2] = 1;
    id<MTLBuffer> arguments = [device newBufferWithLength:encoder.encodedLength options:MTLResourceStorageModeShared];
    MTLTextureDescriptor *target_desc =
        [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA32Float
                                                           width:1
                                                          height:1
                                                       mipmapped:NO];
    target_desc.storageMode = MTLStorageModeShared;
    target_desc.usage = MTLTextureUsageRenderTarget;
    id<MTLTexture> target = [device newTextureWithDescriptor:target_desc];
    id<MTLCommandQueue> queue = [device newCommandQueue];
    if (!arguments || !target || !queue) {
        fprintf(stderr, "local fragment resources unavailable\n");
        return 22;
    }
    for (int draw = 0; draw < 5; draw++) {
        int sampling = draw != 0;
        ((uint32_t *)buffers[3].contents)[2 * 4 + 3] = sampling ? 1 : 0;
        ((uint32_t *)typed.contents)[0] = sampling ? 0x3f800001u : 0;
        float *storage = buffers[5].contents;
        storage[41] = storage[43] = storage[45] = storage[47] = 1.f;
        storage[49] = storage[51] = storage[53] = storage[55] = 1.f;
        storage[38] = storage[63] = 1.f;
        ((uint32_t *)storage)[32] = draw == 3 ? 31 : draw == 4 ? 0 : 7;
        float *constants = buffers[3].contents;
        constants[40 * 4] = constants[40 * 4 + 1] = constants[40 * 4 + 2] = constants[40 * 4 + 3] = 1.f;
        memset(arguments.contents, 0, arguments.length);
        [encoder setArgumentBuffer:arguments offset:0];
        for (int i = 0; i < 6; i++)
            [encoder setBuffer:buffers[i] offset:0 atIndex:(NSUInteger)i];
        [encoder setTexture:depth atIndex:6];
        [encoder setSamplerState:sampler atIndex:7];
        [encoder setTexture:buf0 atIndex:8];
        [encoder setTexture:tex2d atIndex:9];
        [encoder setSamplerState:sampler atIndex:10];
        [encoder setTexture:buf1 atIndex:11];
        probe_resources resources = {0};
        uint64_t handles[32];
        resources.sampler = sampler.gpuResourceID._impl;
        for (int i = 0; i < 32; i++) {
            int offset = (draw == 2) || (draw == 1 && getenv("HOGWARTS_PROBE_BAD_FRAGMENT_TEXTURE"));
            resources.textures[i + 1] = textures[i].gpuResourceID._impl;
            handles[i] = (uint32_t)((i + offset) % 32 + 1);
            [encoder setTexture:textures[(i + offset) % 32] atIndex:(NSUInteger)(12 + i)];
            [encoder setSamplerState:sampler atIndex:(NSUInteger)(44 + i)];
        }
        if (nvn_indirect_texture_bind(handles, sizeof handles, 32, 1u << 20, arguments.contents,
                                      arguments.length / sizeof(uint64_t), 12, 44, resolve_resource, &resources,
                                      NULL) != NVN_INDIRECT_OK) {
            fprintf(stderr, "local fragment indirect binding failed\n");
            return 28;
        }
        id<MTLCommandBuffer> commands = [queue commandBuffer];
        MTLRenderPassDescriptor *depth_pass = [MTLRenderPassDescriptor renderPassDescriptor];
        depth_pass.depthAttachment.texture = depth;
        depth_pass.depthAttachment.clearDepth = .25;
        depth_pass.depthAttachment.loadAction = MTLLoadActionClear;
        depth_pass.depthAttachment.storeAction = MTLStoreActionStore;
        id<MTLRenderCommandEncoder> clear = [commands renderCommandEncoderWithDescriptor:depth_pass];
        if (!clear) {
            fprintf(stderr, "local fragment depth clear failed\n");
            return 23;
        }
        [clear endEncoding];
        MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
        pass.colorAttachments[0].texture = target;
        pass.colorAttachments[0].clearColor = MTLClearColorMake(1, 0, 1, 0);
        pass.colorAttachments[0].loadAction = MTLLoadActionClear;
        pass.colorAttachments[0].storeAction = MTLStoreActionStore;
        id<MTLRenderCommandEncoder> render = [commands renderCommandEncoderWithDescriptor:pass];
        if (!render) {
            fprintf(stderr, "local fragment render encoder failed\n");
            return 24;
        }
        [render setRenderPipelineState:pipeline];
        [render setFragmentBuffer:arguments offset:0 atIndex:0];
        for (id<MTLBuffer> buffer in buffers)
            [render useResource:buffer usage:MTLResourceUsageRead stages:MTLRenderStageFragment];
        for (id<MTLTexture> texture in textures)
            [render useResource:texture usage:MTLResourceUsageRead stages:MTLRenderStageFragment];
        [render useResource:depth usage:MTLResourceUsageRead stages:MTLRenderStageFragment];
        [render useResource:tex2d usage:MTLResourceUsageRead stages:MTLRenderStageFragment];
        [render useResource:typed usage:MTLResourceUsageRead stages:MTLRenderStageFragment];
        [render useResource:buf0 usage:MTLResourceUsageRead stages:MTLRenderStageFragment];
        [render useResource:buf1 usage:MTLResourceUsageRead stages:MTLRenderStageFragment];
        [render drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
        [render endEncoding];
        [commands commit];
        [commands waitUntilCompleted];
        if (commands.status != MTLCommandBufferStatusCompleted) {
            fprintf(stderr, "local fragment GPU command: %s\n", commands.error.localizedDescription.UTF8String);
            return 25;
        }
        float pixel[4] = {0};
        [target getBytes:pixel bytesPerRow:sizeof pixel fromRegion:MTLRegionMake2D(0, 0, 1, 1) mipmapLevel:0];
        const float values[] = {0.f, 8.f, 9.f, 32.f, 1.f};
        const float expected[] = {values[draw], 0.f, 0.f, 1.f};
        if (getenv("HOGWARTS_PROBE_BAD_FRAGMENT_EXPECTED"))
            pixel[0] = 1.f;
        if (!check_results(pixel, expected, 4) || !isfinite(pixel[0]) || !isfinite(pixel[1]) || !isfinite(pixel[2]) ||
            !isfinite(pixel[3])) {
            fprintf(stderr, "local fragment pixel: %.3f %.3f %.3f %.3f; expected %.3f 0 0 1\n", pixel[0], pixel[1],
                    pixel[2], pixel[3], expected[0]);
            return 26;
        }
    }
    return 0;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc != 1 && argc != 3) {
            fprintf(stderr, "usage: probe [local-shader.metal local-reflection.json]\n");
            return 1;
        }
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device || device.argumentBuffersSupport != MTLArgumentBuffersTier2) {
            fprintf(stderr, "Metal tier 2 argument buffers are required\n"); return 1;
        }
        NSString *source = @"#include <metal_stdlib>\nusing namespace metal;\n"
            "struct Args { constant uint *p0 [[id(0)]]; constant uint *p1 [[id(1)]]; "
            "constant uint *p2 [[id(2)]]; constant uint *p3 [[id(3)]]; "
            "constant uint *p4 [[id(4)]]; device const uint *p5 [[id(5)]]; "
            "depth2d<float> depth [[id(6)]]; sampler depth_sampler [[id(7)]]; "
            "texture_buffer<float> buf0 [[id(8)]]; texture2d<float> tex2d [[id(9)]]; "
            "sampler tex_sampler [[id(10)]]; texture_buffer<float> buf1 [[id(11)]]; "
            "array<texture3d<float>, 32> textures [[id(12)]]; "
            "array<sampler, 32> samplers [[id(44)]]; };\n"
            "kernel void test(constant Args& a [[buffer(0)]], device const uint *idx [[buffer(1)]], "
            "device float *out [[buffer(2)]], uint tid [[thread_position_in_grid]]) { "
            "uint sum = *a.p0 + *a.p1 + *a.p2 + *a.p3 + *a.p4 + *a.p5; "
            "uint i = idx[tid]; out[tid] = a.textures[i].sample(a.samplers[i], float3(0.5)).x + sum + "
            "a.depth.sample(a.depth_sampler, float2(0.5)) + a.buf0.read(0u).x + "
            "a.tex2d.sample(a.tex_sampler, float2(0.5)).x + 2.0 * a.buf1.read(0u).x; }";
        NSError *error = nil;
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        if (!library) { fprintf(stderr, "shader: %s\n", error.localizedDescription.UTF8String); return 2; }
        id<MTLFunction> fn = [library newFunctionWithName:@"test"];
        id<MTLComputePipelineState> pipeline = [device newComputePipelineStateWithFunction:fn error:&error];
        if (!pipeline) { fprintf(stderr, "pipeline: %s\n", error.localizedDescription.UTF8String); return 3; }
        id<MTLArgumentEncoder> encoder = [fn newArgumentEncoderWithBufferIndex:0];
        id<MTLArgumentEncoder> real_encoder = nil;
        id<MTLFunction> real_fn = nil;
        if (argc == 3) {
            NSString *shader_path = [NSString stringWithUTF8String:argv[1]];
            NSString *reflection_path = [NSString stringWithUTF8String:argv[2]];
            NSString *real_source = [NSString stringWithContentsOfFile:shader_path encoding:NSUTF8StringEncoding error:&error];
            NSData *json_data = [NSData dataWithContentsOfFile:reflection_path options:0 error:&error];
            id json = json_data ? [NSJSONSerialization JSONObjectWithData:json_data options:0 error:&error] : nil;
            if (!real_source || ![json isKindOfClass:[NSDictionary class]] ||
                ![json[@"entry"] isKindOfClass:[NSString class]]) {
                fprintf(stderr, "local shader or reflection unavailable: %s\n", error.localizedDescription.UTF8String ?: "invalid entry");
                return 14;
            }
            if (getenv("HOGWARTS_PROBE_RUN_LOCAL_FRAGMENT")) {
                NSData *source_bytes = [real_source dataUsingEncoding:NSUTF8StringEncoding];
                unsigned char hash[CC_SHA256_DIGEST_LENGTH];
                static const unsigned char expected_hash[CC_SHA256_DIGEST_LENGTH] = {
                    0xf7, 0x4d, 0x6f, 0xa1, 0xf1, 0x13, 0x2f, 0xe1, 0x97, 0x33, 0xc7, 0x57, 0xc3, 0xcb, 0x0d, 0xf8,
                    0x66, 0xa5, 0x8e, 0xea, 0x5f, 0x14, 0xbf, 0xf4, 0xef, 0xab, 0x8a, 0x3f, 0xf3, 0x62, 0x60, 0x42,
                };
                if (!source_bytes || source_bytes.length > UINT32_MAX ||
                    ![json[@"entry"] isEqualToString:@"main0"] ||
                    !CC_SHA256(source_bytes.bytes, (CC_LONG)source_bytes.length, hash) ||
                    memcmp(hash, expected_hash, sizeof hash)) {
                    fprintf(stderr, "local fragment probe requires the pinned observed shader and entry\n");
                    return 27;
                }
            }
            id<MTLLibrary> real_library = [device newLibraryWithSource:real_source options:nil error:&error];
            if (!real_library) { fprintf(stderr, "local shader compilation failed: %s\n", error.localizedDescription.UTF8String); return 15; }
            real_fn = [real_library newFunctionWithName:json[@"entry"]];
            if (!real_fn || real_fn.functionType != MTLFunctionTypeFragment) {
                fprintf(stderr, "local shader entry is not a fragment function\n"); return 16;
            }
            real_encoder = [real_fn newArgumentEncoderWithBufferIndex:0];
            if (!real_encoder || real_encoder.encodedLength != 76 * sizeof(uint64_t)) {
                fprintf(stderr, "local shader argument layout mismatch: %lu\n", (unsigned long)real_encoder.encodedLength);
                return 17;
            }
        }
        nvn_refl reflection = {0};
        const uint8_t kinds[] = {NVN_RB_SUPPORT, NVN_RB_CBUF, NVN_RB_CBUF, NVN_RB_CBUF,
            NVN_RB_C1, NVN_RB_SBUFP, NVN_RB_TEX, NVN_RB_SAMP, NVN_RB_TBUF,
            NVN_RB_TEX, NVN_RB_SAMP, NVN_RB_TBUF, NVN_RB_ITEX, NVN_RB_ISAMP};
        const uint16_t aids[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 44};
        reflection.nb = 14;
        for (int i = 0; i < reflection.nb; i++)
            reflection.b[i] = (nvn_rbind){.kind = kinds[i], .aid = aids[i],
                .indirect_count = (uint8_t)(i >= 12 ? 32 : 0)};
        int slot_count = nvn_refl_argument_slots(&reflection);
        if (!encoder || slot_count != 76 || encoder.encodedLength != (NSUInteger)slot_count * sizeof(uint64_t)) {
            fprintf(stderr, "unexpected argument buffer layout: encoder=%s length=%lu\n",
                    encoder ? "present" : "missing", (unsigned long)encoder.encodedLength); return 4;
        }
        MTLTextureDescriptor *desc = [[MTLTextureDescriptor alloc] init];
        desc.textureType = MTLTextureType3D;
        desc.pixelFormat = MTLPixelFormatR32Float;
        desc.width = desc.height = desc.depth = 1;
        desc.storageMode = MTLStorageModeShared;
        desc.usage = MTLTextureUsageShaderRead;
        NSMutableArray<id<MTLTexture>> *textures = [NSMutableArray array];
        for (int i = 0; i < 32; i++) {
            id<MTLTexture> tex = [device newTextureWithDescriptor:desc];
            if (!tex) { fprintf(stderr, "texture %d allocation failed\n", i); return 5; }
            float value = (float)(i + 1);
            [tex replaceRegion:MTLRegionMake3D(0, 0, 0, 1, 1, 1) mipmapLevel:0 slice:0
                     withBytes:&value bytesPerRow:sizeof value bytesPerImage:sizeof value];
            [textures addObject:tex];
        }
        MTLSamplerDescriptor *sd = [[MTLSamplerDescriptor alloc] init];
        sd.minFilter = sd.magFilter = MTLSamplerMinMagFilterNearest;
        sd.supportArgumentBuffers = YES;
        id<MTLSamplerState> sampler = [device newSamplerStateWithDescriptor:sd];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        const uint32_t indices[] = {0, 1, 7, 31};
        id<MTLBuffer> indexBuffer = [device newBufferWithBytes:indices length:sizeof indices
                                                       options:MTLResourceStorageModeShared];
        MTLTextureDescriptor *d2 = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatR32Float width:1 height:1 mipmapped:NO];
        d2.storageMode = MTLStorageModeShared; d2.usage = MTLTextureUsageShaderRead;
        id<MTLTexture> tex2d = [device newTextureWithDescriptor:d2];
        float tex2d_value = .5f;
        [tex2d replaceRegion:MTLRegionMake2D(0,0,1,1) mipmapLevel:0 withBytes:&tex2d_value bytesPerRow:4];
        MTLTextureDescriptor *depth_desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatDepth32Float width:1 height:1 mipmapped:NO];
        depth_desc.storageMode = MTLStorageModePrivate;
        depth_desc.usage = MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget;
        id<MTLTexture> depth = [device newTextureWithDescriptor:depth_desc];
        NSUInteger alignment = [device minimumLinearTextureAlignmentForPixelFormat:MTLPixelFormatR32Float];
        if (alignment < 256) alignment = 256;
        id<MTLBuffer> typed = [device newBufferWithLength:alignment * 2 options:MTLResourceStorageModeShared];
        MTLTextureDescriptor *buffer_desc = [MTLTextureDescriptor textureBufferDescriptorWithPixelFormat:MTLPixelFormatR32Float width:1
            resourceOptions:MTLResourceStorageModeShared usage:MTLTextureUsageShaderRead];
        id<MTLTexture> buf0 = [typed newTextureWithDescriptor:buffer_desc offset:0 bytesPerRow:alignment];
        id<MTLTexture> buf1 = [typed newTextureWithDescriptor:buffer_desc offset:alignment bytesPerRow:alignment];
        if (!sampler || !queue || !indexBuffer || !tex2d || !depth || !typed || !buf0 || !buf1) {
            fprintf(stderr, "mixed resource allocation failed\n"); return 6;
        }
        *(float *)typed.contents = 2.f;
        *(float *)((uint8_t *)typed.contents + alignment) = 3.f;
        if (real_fn && getenv("HOGWARTS_PROBE_RUN_LOCAL_FRAGMENT")) {
            *(float *)typed.contents = 0.f;
            int result = run_local_fragment(device, real_fn, real_encoder, textures, sampler, depth, tex2d, buf0, buf1, typed);
            *(float *)typed.contents = 2.f;
            if (result) return result;
        }
        probe_resources resources = {0};
        for (int i = 0; i < 32; i++) resources.textures[i + 1] = textures[i].gpuResourceID._impl;
        resources.sampler = sampler.gpuResourceID._impl;
        for (int pass = 0; pass < 2; pass++) {
            id<MTLBuffer> args = [device newBufferWithLength:encoder.encodedLength options:MTLResourceStorageModeShared];
            id<MTLBuffer> reference = [device newBufferWithLength:encoder.encodedLength options:MTLResourceStorageModeShared];
            id<MTLBuffer> output = [device newBufferWithLength:sizeof indices options:MTLResourceStorageModeShared];
            if (!args || !reference || !output) { fprintf(stderr, "buffer allocation failed\n"); return 7; }
            memset(args.contents, 0, args.length);
            memset(reference.contents, 0, reference.length);
            uint64_t *slots = args.contents;
            [encoder setArgumentBuffer:reference offset:0];
            for (int i = 0; i < 6; i++) {
                slots[i] = indexBuffer.gpuAddress;
                [encoder setBuffer:indexBuffer offset:0 atIndex:(NSUInteger)i];
            }
            slots[6] = depth.gpuResourceID._impl; [encoder setTexture:depth atIndex:6];
            slots[7] = sampler.gpuResourceID._impl; [encoder setSamplerState:sampler atIndex:7];
            slots[8] = buf0.gpuResourceID._impl; [encoder setTexture:buf0 atIndex:8];
            slots[9] = tex2d.gpuResourceID._impl; [encoder setTexture:tex2d atIndex:9];
            slots[10] = sampler.gpuResourceID._impl; [encoder setSamplerState:sampler atIndex:10];
            slots[11] = buf1.gpuResourceID._impl; [encoder setTexture:buf1 atIndex:11];
            uint64_t handles[32];
            for (int i = 0; i < 32; i++) {
                handles[i] = (uint32_t)((i + pass) % 32 + 1);
                [encoder setTexture:textures[(i + pass) % 32] atIndex:(NSUInteger)(12 + i)];
                [encoder setSamplerState:sampler atIndex:(NSUInteger)(44 + i)];
            }
            if (nvn_indirect_texture_bind(handles, sizeof handles, 32, 1u << 20,
                                          slots, args.length / sizeof *slots, 12, 44,
                                          resolve_resource, &resources, NULL) != NVN_INDIRECT_OK) {
                fprintf(stderr, "indirect binding failed\n"); return 13;
            }
            if (memcmp(args.contents, reference.contents, args.length)) {
                fprintf(stderr, "direct argument buffer differs from Metal encoder\n"); return 12;
            }
            if (real_encoder) {
                id<MTLBuffer> real_reference = [device newBufferWithLength:real_encoder.encodedLength options:MTLResourceStorageModeShared];
                if (!real_reference) { fprintf(stderr, "local shader argument buffer allocation failed\n"); return 18; }
                memset(real_reference.contents, 0, real_reference.length);
                [real_encoder setArgumentBuffer:real_reference offset:0];
                for (int i = 0; i < 6; i++) [real_encoder setBuffer:indexBuffer offset:0 atIndex:(NSUInteger)i];
                [real_encoder setTexture:depth atIndex:6]; [real_encoder setSamplerState:sampler atIndex:7];
                [real_encoder setTexture:buf0 atIndex:8]; [real_encoder setTexture:tex2d atIndex:9];
                [real_encoder setSamplerState:sampler atIndex:10]; [real_encoder setTexture:buf1 atIndex:11];
                for (int i = 0; i < 32; i++) {
                    [real_encoder setTexture:textures[(i + pass) % 32] atIndex:(NSUInteger)(12 + i)];
                    [real_encoder setSamplerState:sampler atIndex:(NSUInteger)(44 + i)];
                }
                if (getenv("HOGWARTS_PROBE_BAD_REAL_LAYOUT")) {
                    uint64_t *real_slots = real_reference.contents;
                    uint64_t tmp = real_slots[8]; real_slots[8] = real_slots[11]; real_slots[11] = tmp;
                }
                if (memcmp(args.contents, real_reference.contents, args.length)) {
                    fprintf(stderr, "local shader argument buffer differs from decoded slots\n"); return 19;
                }
            }
            if (getenv("HOGWARTS_PROBE_SWAP_TYPED_BUFFERS")) {
                uint64_t tmp = slots[8]; slots[8] = slots[11]; slots[11] = tmp;
            }
            id<MTLCommandBuffer> commands = [queue commandBuffer];
            MTLRenderPassDescriptor *depth_pass = [MTLRenderPassDescriptor renderPassDescriptor];
            depth_pass.depthAttachment.texture = depth;
            depth_pass.depthAttachment.clearDepth = .25;
            depth_pass.depthAttachment.loadAction = MTLLoadActionClear;
            depth_pass.depthAttachment.storeAction = MTLStoreActionStore;
            id<MTLRenderCommandEncoder> depth_encoder = [commands renderCommandEncoderWithDescriptor:depth_pass];
            if (!depth_encoder) { fprintf(stderr, "depth clear encoder creation failed\n"); return 8; }
            [depth_encoder endEncoding];
            id<MTLComputeCommandEncoder> compute = [commands computeCommandEncoder];
            if (!commands || !compute) { fprintf(stderr, "command encoder creation failed\n"); return 8; }
            [compute setComputePipelineState:pipeline];
            [compute setBuffer:args offset:0 atIndex:0];
            [compute setBuffer:indexBuffer offset:0 atIndex:1];
            [compute setBuffer:output offset:0 atIndex:2];
            [compute useResource:indexBuffer usage:MTLResourceUsageRead];
            for (id<MTLTexture> tex in textures) [compute useResource:tex usage:MTLResourceUsageRead];
            [compute useResource:depth usage:MTLResourceUsageRead];
            [compute useResource:tex2d usage:MTLResourceUsageRead];
            [compute useResource:typed usage:MTLResourceUsageRead];
            [compute useResource:buf0 usage:MTLResourceUsageRead];
            [compute useResource:buf1 usage:MTLResourceUsageRead];
            [compute dispatchThreads:MTLSizeMake(4, 1, 1) threadsPerThreadgroup:MTLSizeMake(4, 1, 1)];
            [compute endEncoding];
            [commands commit];
            [commands waitUntilCompleted];
            if (commands.status != MTLCommandBufferStatusCompleted) {
                fprintf(stderr, "GPU command: %s\n", commands.error.localizedDescription.UTF8String); return 9;
            }
            float expected[4];
            for (int i = 0; i < 4; i++) expected[i] = (float)((indices[i] + pass) % 32 + 1) + 8.75f;
            if (!check_results(output.contents, expected, 4)) {
                const float *actual = output.contents;
                fprintf(stderr, "pass %d: got %.2f %.2f %.2f %.2f; expected %.2f %.2f %.2f %.2f\n",
                        pass, actual[0], actual[1], actual[2], actual[3],
                        expected[0], expected[1], expected[2], expected[3]);
                return 10;
            }
            expected[0] += 1;
            if (check_results(output.contents, expected, 4)) {
                fprintf(stderr, "negative control unexpectedly passed\n"); return 11;
            }
        }
        return 0;
    }
}
