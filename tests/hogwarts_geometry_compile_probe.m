#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdio.h>

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc != 4) { fprintf(stderr, "expected vsc, gsc and vpt Metal source paths\n"); return 1; }
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) { fprintf(stderr, "Metal device unavailable\n"); return 2; }
        for (int i = 1; i < argc; i++) {
            NSError *error = nil;
            NSString *source = [NSString stringWithContentsOfFile:@(argv[i])
                                                          encoding:NSUTF8StringEncoding error:&error];
            if (!source) { fprintf(stderr, "read source: %s\n", error.localizedDescription.UTF8String); return 3; }
            id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
            id<MTLFunction> function = [library newFunctionWithName:@"main0"];
            MTLFunctionType expected = i == 3 ? MTLFunctionTypeVertex : MTLFunctionTypeKernel;
            if (!library || !function || function.functionType != expected) {
                fprintf(stderr, "geometry stage %d compile: %s\n", i,
                        error.localizedDescription.UTF8String ?: "missing or wrong entry point");
                return 4;
            }
            if (i != 3 && ![device newComputePipelineStateWithFunction:function error:&error]) {
                fprintf(stderr, "geometry stage %d pipeline: %s\n", i, error.localizedDescription.UTF8String);
                return 5;
            }
        }
        return 0;
    }
}
