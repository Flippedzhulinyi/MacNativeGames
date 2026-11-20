#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdio.h>

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) { fprintf(stderr, "no Metal device\n"); return 1; }
        MTLTextureDescriptor *desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatDepth32Float_Stencil8 width:2 height:2 mipmapped:NO];
        desc.storageMode = MTLStorageModePrivate;
        desc.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead | MTLTextureUsagePixelFormatView;
        id<MTLTexture> texture = [device newTextureWithDescriptor:desc];
        id<MTLTexture> view = [texture newTextureViewWithPixelFormat:MTLPixelFormatX32_Stencil8];
        if (!view) { fprintf(stderr, "cannot create stencil-plane view\n"); return 2; }
        NSString *source = @"#include <metal_stdlib>\nusing namespace metal;\n"
            "kernel void read_stencil(texture2d<uint, access::read> t [[texture(0)]], "
            "device uint *out [[buffer(0)]], uint2 p [[thread_position_in_grid]]) { out[p.y*2+p.x] = t.read(p).x; }";
        NSError *error = nil;
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        if (!library) { fprintf(stderr, "shader: %s\n", error.localizedDescription.UTF8String); return 3; }
        id<MTLComputePipelineState> pipeline = [device newComputePipelineStateWithFunction:[library newFunctionWithName:@"read_stencil"] error:&error];
        if (!pipeline) { fprintf(stderr, "pipeline: %s\n", error.localizedDescription.UTF8String); return 4; }
        id<MTLBuffer> buffer = [device newBufferWithLength:4 * sizeof(uint32_t) options:MTLResourceStorageModeShared];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        id<MTLCommandBuffer> commands = [queue commandBuffer];
        MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
        pass.depthAttachment.texture = texture;
        pass.depthAttachment.loadAction = MTLLoadActionClear;
        pass.depthAttachment.storeAction = MTLStoreActionStore;
        pass.depthAttachment.clearDepth = 1.0;
        pass.stencilAttachment.texture = texture;
        pass.stencilAttachment.loadAction = MTLLoadActionClear;
        pass.stencilAttachment.storeAction = MTLStoreActionStore;
        pass.stencilAttachment.clearStencil = 0x5a;
        id<MTLRenderCommandEncoder> render = [commands renderCommandEncoderWithDescriptor:pass];
        if (!render) { fprintf(stderr, "cannot create render encoder\n"); return 5; }
        [render endEncoding];
        id<MTLComputeCommandEncoder> compute = [commands computeCommandEncoder];
        [compute setComputePipelineState:pipeline];
        [compute setTexture:view atIndex:0];
        [compute setBuffer:buffer offset:0 atIndex:0];
        [compute dispatchThreads:MTLSizeMake(2, 2, 1) threadsPerThreadgroup:MTLSizeMake(2, 2, 1)];
        [compute endEncoding];
        [commands commit];
        [commands waitUntilCompleted];
        if (commands.status != MTLCommandBufferStatusCompleted) {
            fprintf(stderr, "GPU command: %s\n", commands.error.localizedDescription.UTF8String);
            return 6;
        }
        const uint32_t *pixels = buffer.contents;
        for (int i = 0; i < 4; i++) if (pixels[i] != 0x5a) {
            fprintf(stderr, "stencil pixel %d: %#x, expected 0x5a\n", i, pixels[i]); return 7;
        }
        return 0;
    }
}
