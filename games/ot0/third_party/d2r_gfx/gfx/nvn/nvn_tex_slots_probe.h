/* Included by nvn_mtl.m: production encode_args, descriptor publication and GPU
   pixel checks. Inputs are immutable until mtl_finish. Probe caches stay isolated. */
static void indirect_registry_sample(uint64_t slots[4], id<MTLTexture> tex, float expected) {
    NSError *error = nil;
    NSString *source = @"#include <metal_stdlib>\nusing namespace metal;\n"
        "struct A { array<texture3d<float>, 2> t [[id(0)]]; array<sampler, 2> s [[id(2)]]; }; "
        "kernel void test(constant A &a [[buffer(0)]], device float *out [[buffer(1)]], "
        "uint i [[thread_position_in_grid]]) { out[i] = a.t[i].sample(a.s[i], float3(0.5)).x; } "
        "vertex float4 vs(uint i [[vertex_id]]) { float2 p[3] = {float2(-1,-1),float2(3,-1),float2(-1,3)}; return float4(p[i],0,1); } "
        "fragment float4 fs(constant A &a [[buffer(0)]], float4 p [[position]]) { "
        "uint i = uint(p.x); return a.t[i].sample(a.s[i], float3(0.5)); }";
    id<MTLLibrary> lib = [g_dev newLibraryWithSource:source options:nil error:&error];
    id<MTLFunction> fn = lib ? [lib newFunctionWithName:@"test"] : nil;
    id<MTLComputePipelineState> ps = fn ? [g_dev newComputePipelineStateWithFunction:fn error:&error] : nil;
    id<MTLArgumentEncoder> ae = fn ? [fn newArgumentEncoderWithBufferIndex:0] : nil;
    if (!ps || !ae || ae.encodedLength != sizeof(uint64_t) * 4)
        MDIE("indirect registry probe shader: %s", error.localizedDescription.UTF8String);
    id<MTLBuffer> args = [g_dev newBufferWithBytes:slots length:sizeof(uint64_t) * 4 options:MTLResourceStorageModeShared];
    id<MTLBuffer> out = [g_dev newBufferWithLength:sizeof(float) * 2 options:MTLResourceStorageModeShared];
    id<MTLCommandQueue> queue = [g_dev newCommandQueue];
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLComputeCommandEncoder> ce = [cb computeCommandEncoder];
    if (!args || !out || !queue || !cb || !ce) MDIE("indirect registry probe command allocation");
    [ce setComputePipelineState:ps]; [ce setBuffer:args offset:0 atIndex:0];
    [ce setBuffer:out offset:0 atIndex:1]; [ce useResource:tex usage:MTLResourceUsageRead];
    [ce dispatchThreads:MTLSizeMake(2,1,1) threadsPerThreadgroup:MTLSizeMake(2,1,1)];
    [ce endEncoding]; [cb commit]; [cb waitUntilCompleted];
    if (cb.status != MTLCommandBufferStatusCompleted)
        MDIE("indirect registry probe GPU: %s", cb.error.localizedDescription.UTF8String);
    float *result = out.contents;
    if (fabsf(result[0] - expected) > 0.0001f || fabsf(result[1] - expected) > 0.0001f)
        MDIE("indirect registry probe pixels %g %g expected %g", result[0], result[1], expected);
    MTLTextureDescriptor *d = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA32Float width:2 height:1 mipmapped:NO];
    d.storageMode = MTLStorageModeShared; d.usage = MTLTextureUsageRenderTarget;
    id<MTLTexture> output = [g_dev newTextureWithDescriptor:d];
    MTLRenderPipelineDescriptor *pd = [MTLRenderPipelineDescriptor new];
    pd.vertexFunction = [lib newFunctionWithName:@"vs"]; pd.fragmentFunction = [lib newFunctionWithName:@"fs"];
    pd.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA32Float;
    id<MTLRenderPipelineState> renderPS = [g_dev newRenderPipelineStateWithDescriptor:pd error:&error];
    MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture = output;
    pass.colorAttachments[0].loadAction = MTLLoadActionDontCare;
    pass.colorAttachments[0].storeAction = MTLStoreActionStore;
    cb = [queue commandBuffer];
    id<MTLRenderCommandEncoder> render = output && renderPS ? [cb renderCommandEncoderWithDescriptor:pass] : nil;
    if (!render) MDIE("indirect registry probe render: %s", error.localizedDescription.UTF8String);
    [render setRenderPipelineState:renderPS]; [render setFragmentBuffer:args offset:0 atIndex:0];
    [render useResource:tex usage:MTLResourceUsageRead stages:MTLRenderStageFragment];
    [render drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    [render endEncoding]; [cb commit]; [cb waitUntilCompleted];
    if (cb.status != MTLCommandBufferStatusCompleted)
        MDIE("indirect registry probe fragment GPU: %s", cb.error.localizedDescription.UTF8String);
    float pixels[8];
    [output getBytes:pixels bytesPerRow:sizeof pixels fromRegion:MTLRegionMake2D(0,0,2,1) mipmapLevel:0];
    if (fabsf(pixels[0] - expected) > 0.0001f || fabsf(pixels[4] - expected) > 0.0001f)
        MDIE("indirect registry probe fragment pixels %g %g expected %g", pixels[0], pixels[4], expected);
}

int mtl_probe_tex_slots(void) {
    mtl_init(); int checked = 0;
    const char *ne = getenv("TOTK_PROBE_NEGATIVE"); int negative = ne ? atoi(ne) : 0;
    void *mem = NULL;
    if (posix_memalign(&mem, 16384, 16384) || !mem) MDIE("texture slots probe memory");
    memset(mem, 0, 16384); mtl_pool_add(mem, 16384);
    for (int i = 0; i < 16; i++) ((float *)((uint8_t *)mem + 16*i))[0] = i & 1 ? .75f : .25f;
    const uint8_t pixels[3][8] = {{64,128,192,255,192,64,128,255},
        {32,96,160,255,160,32,96,255}, {96,160,32,255,32,96,160,255}};
    samp_par clamp = {.lod_max=16,.aniso=1}, repeat = clamp; repeat.ws = 1;
    id<MTLTexture> sources[3], output;
    id<MTLBuffer> typed = probe_buf(3*256), rb = probe_buf(2048);
    NSError *error = nil;
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:64 height:8 mipmapped:NO];
    td.storageMode = MTLStorageModePrivate; td.usage = MTLTextureUsageRenderTarget;
    output = [g_dev newTextureWithDescriptor:td]; res_add(output);
    op_hdr end = {OP_END,8};
    if (!negative) {
        MTLTextureDescriptor *d = [MTLTextureDescriptor new];
        d.textureType = MTLTextureType3D; d.pixelFormat = MTLPixelFormatR32Float;
        d.width = d.height = d.depth = 1; d.storageMode = MTLStorageModeShared;
        d.usage = MTLTextureUsageShaderRead;
        id<MTLTexture> a = [g_dev newTextureWithDescriptor:d], b = [g_dev newTextureWithDescriptor:d];
        if (!a || !b) MDIE("indirect registry probe texture allocation");
        float av = 0.25f, bv = 0.75f;
        [a replaceRegion:MTLRegionMake3D(0,0,0,1,1,1) mipmapLevel:0 slice:0 withBytes:&av bytesPerRow:4 bytesPerImage:4];
        [b replaceRegion:MTLRegionMake3D(0,0,0,1,1,1) mipmapLevel:0 slice:0 withBytes:&bv bytesPerRow:4 bytesPerImage:4];
        res_add(a); res_add(b);
        tex_t ta = {0}, tb = {0};
        ta.serial = 0xfffed101; tb.serial = 0xfffed102;
        ta.d = (nvn_texdesc){.width=1,.height=1,.depth=1,.levels=1,.target=NVN_TEXTURE_TARGET_3D};
        tb.d = ta.d;
        serial_put(ta.serial,a); serial_put(tb.serial,b);
        mtl_reg_tex(71,&ta,NULL); mtl_reg_samp(73,&clamp);
        uint64_t handles[2] = {71,71}, slots[4] = {0}, previous[4] = {0};
        registry_lock();
        int r = nvn_indirect_texture_bind(handles,sizeof handles,2,73u<<20,slots,4,0,2,
                                           indirect_resolve_registered,NULL,NULL);
        registry_unlock();
        if (r != NVN_INDIRECT_OK || slots[0] != a.gpuResourceID._impl || slots[1] != slots[0] ||
            !slots[2] || slots[2] != slots[3]) MDIE("indirect registry probe initial bindings");
        indirect_registry_sample(slots,a,av);
        checked += 4;
        mtl_reg_tex(71,&tb,NULL);
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,73u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,NULL);
        registry_unlock();
        if (r != NVN_INDIRECT_OK || slots[0] != b.gpuResourceID._impl) MDIE("indirect registry probe replacement");
        indirect_registry_sample(slots,b,bv);
        checked++;
        d.pixelFormat = MTLPixelFormatBGRA8Unorm;
        id<MTLTexture> bgra = [g_dev newTextureWithDescriptor:d];
        if (!bgra) MDIE("indirect registry probe BGRA allocation");
        const uint8_t bgra_pixel[] = {64, 128, 192, 255};
        [bgra replaceRegion:MTLRegionMake3D(0,0,0,1,1,1) mipmapLevel:0 slice:0
                  withBytes:bgra_pixel bytesPerRow:4 bytesPerImage:4];
        res_add(bgra);
        tex_t bgra_guest = ta; bgra_guest.serial = 0xfffed106;
        serial_put(bgra_guest.serial,bgra); mtl_reg_tex(71,&bgra_guest,NULL);
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,73u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,NULL);
        registry_unlock();
        if (r != NVN_INDIRECT_OK || slots[0] != bgra.gpuResourceID._impl)
            MDIE("indirect registry probe BGRA bindings");
        indirect_registry_sample(slots,bgra,192.0f / 255.0f);
        checked++;
        d.pixelFormat = MTLPixelFormatR32Float;
        memcpy(previous,slots,sizeof slots); handles[1] = 9999;
        unsigned failed = 9;
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,73u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,&failed);
        registry_unlock();
        if (r != NVN_INDIRECT_RESOURCE_UNAVAILABLE || failed != 1 || memcmp(slots,previous,sizeof slots))
            MDIE("indirect registry probe invalid descriptor");
        handles[1] = 71;
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,74u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,&failed);
        registry_unlock();
        if (r != NVN_INDIRECT_RESOURCE_UNAVAILABLE || memcmp(slots,previous,sizeof slots))
            MDIE("indirect registry probe invalid sampler");
        id<MTLTexture> unresident = [g_dev newTextureWithDescriptor:d];
        if (!unresident) MDIE("indirect registry probe unresident allocation");
        tex_t tc = ta; tc.serial = 0xfffed103;
        serial_put(tc.serial,unresident); mtl_reg_tex(71,&tc,NULL);
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,73u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,&failed);
        registry_unlock();
        if (r != NVN_INDIRECT_RESOURCE_UNAVAILABLE || memcmp(slots,previous,sizeof slots))
            MDIE("indirect registry probe nonresident texture");
        samp_par custom = clamp; custom.ws = 4; custom.border[0] = 0.5f;
        mtl_reg_samp(75,&custom); mtl_reg_tex(71,&ta,NULL);
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,75u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,&failed);
        registry_unlock();
        if (r != NVN_INDIRECT_RESOURCE_UNAVAILABLE || memcmp(slots,previous,sizeof slots))
            MDIE("indirect registry probe custom sampler");
        int saved_pool_n = g_tpool_n; g_tpool_n = 71;
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,73u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,&failed);
        registry_unlock(); g_tpool_n = saved_pool_n;
        if (r != NVN_INDIRECT_RESOURCE_UNAVAILABLE || memcmp(slots,previous,sizeof slots))
            MDIE("indirect registry probe texture pool bounds");
        MTLTextureDescriptor *wrong = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatR32Float width:1 height:1 mipmapped:NO];
        wrong.storageMode = MTLStorageModeShared; wrong.usage = MTLTextureUsageShaderRead;
        id<MTLTexture> tex2d = [g_dev newTextureWithDescriptor:wrong];
        if (!tex2d) MDIE("indirect registry probe 2d texture allocation");
        res_add(tex2d); tc.serial = 0xfffed104;
        serial_put(tc.serial,tex2d); mtl_reg_tex(71,&tc,NULL);
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,73u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,&failed);
        registry_unlock();
        if (r != NVN_INDIRECT_RESOURCE_UNAVAILABLE || memcmp(slots,previous,sizeof slots))
            MDIE("indirect registry probe mismatched texture type");
        d.pixelFormat = MTLPixelFormatR32Uint;
        id<MTLTexture> integer = [g_dev newTextureWithDescriptor:d];
        if (!integer) MDIE("indirect registry probe integer texture allocation");
        res_add(integer); tc.serial = 0xfffed105;
        serial_put(tc.serial,integer); mtl_reg_tex(71,&tc,NULL);
        registry_lock();
        r = nvn_indirect_texture_bind(handles,sizeof handles,2,73u<<20,slots,4,0,2,
                                      indirect_resolve_registered,NULL,&failed);
        registry_unlock();
        if (r != NVN_INDIRECT_RESOURCE_UNAVAILABLE || memcmp(slots,previous,sizeof slots))
            MDIE("indirect registry probe mismatched texture format");
        checked += 9;
        mtl_reg_tex(71,NULL,NULL);
    }
    for (int kind = 0; kind < 3; kind++) {
        tex_t textures[2] = {0};
        for (int i = 0; i < 3; i++) {
            if (kind == 2) {
                memcpy((uint8_t *)typed.contents + i*256, pixels[i], 8);
                MTLTextureDescriptor *d = [MTLTextureDescriptor textureBufferDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:2 resourceOptions:MTLResourceStorageModeShared usage:MTLTextureUsageShaderRead];
                sources[i] = [typed newTextureWithDescriptor:d offset:i*256 bytesPerRow:256];
            } else {
                MTLTextureDescriptor *d = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:2 height:1 mipmapped:NO];
                d.storageMode = MTLStorageModeShared; d.usage = MTLTextureUsageShaderRead | MTLTextureUsagePixelFormatView;
                sources[i] = [g_dev newTextureWithDescriptor:d];
                [sources[i] replaceRegion:MTLRegionMake2D(0,0,2,1) mipmapLevel:0 withBytes:pixels[i] bytesPerRow:8];
            }
            if (!sources[i]) MDIE("texture slots probe resource"); res_add(sources[i]);
        }
        for (int i = 0; i < 2; i++) {
            textures[i].serial = 0xffffe100 + kind*4 + i;
            textures[i].d = (nvn_texdesc){.width=2,.height=1,.depth=1,.levels=1,.format=0x25,.target=kind==2?10:1,
                .swizzle_r=2,.swizzle_g=3,.swizzle_b=4,.swizzle_a=5};
        }
        NSString *fields = kind == 2 ? @"texture_buffer<float> t [[id(0)]]; constant float *u [[id(1)]];" :
            [NSString stringWithFormat:@"%@<float> t [[id(0)]]; sampler a [[id(1)]]; sampler b [[id(2)]]; constant float *u [[id(3)]];",kind ? @"texture2d_array" : @"texture2d"];
        NSString *body = kind == 2 ? @"return float4(a.t.read(0u).rgb,a.u[0]);" :
            [NSString stringWithFormat:@"return float4(a.t.sample(a.a,float2(1.25,0.5)%@).r,a.t.sample(a.b,float2(1.25,0.5)%@).g,a.t.read(uint2(0,0)%@).b,a.u[0]);",kind?@",0":@"",kind?@",0":@"",kind?@",0":@""];
        NSString *source = [NSString stringWithFormat:@"#include <metal_stdlib>\nusing namespace metal; struct A {%@}; vertex float4 vs(uint i [[vertex_id]]){float2 p[3]={float2(-1,-1),float2(3,-1),float2(-1,3)};return float4(p[i],0,1);} fragment float4 fa(constant A &a [[buffer(0)]]){%@} fragment float4 fb(constant A &a [[buffer(0)]]){%@}",fields,body,body];
        id<MTLLibrary> lib = [g_dev newLibraryWithSource:source options:nil error:&error];
        if (!lib) MDIE("texture slots probe shader: %s",error.localizedDescription.UTF8String);
        NvShader *shaders[2]; id<MTLRenderPipelineState> pipelines[2]; prog_t programs[2] = {0};
        for (int i = 0; i < 2; i++) {
            NvShader *sh = [NvShader new]; shaders[i] = sh; sh->fn = [lib newFunctionWithName:i?@"fb":@"fa"]; sh->stage=1;
            snprintf(sh->key,sizeof sh->key,"probe-tex-slots-%d-%d",kind,i);
            sh->rf.nb = kind==2?2:4;
            sh->rf.b[0]=(nvn_rbind){.kind=kind==2?NVN_RB_TBUF:NVN_RB_TEX,.aid=0,.reg=0,.dtt=kind?MTLTextureType2DArray:MTLTextureType2D};
            if(kind!=2) {
                sh->rf.b[1]=(nvn_rbind){.kind=NVN_RB_SAMPT,.aid=1,.reg=0};
                sh->rf.b[2]=(nvn_rbind){.kind=NVN_RB_SAMP,.aid=2,.reg=0};
            }
            sh->rf.b[sh->rf.nb-1]=(nvn_rbind){.kind=NVN_RB_CBUF,.aid=sh->rf.nb-1,.reg=0};
            sh->ae=[sh->fn newArgumentEncoderWithBufferIndex:0]; sh->arg_len=sh->ae.encodedLength;
            if(sh->arg_len != (NSUInteger)sh->rf.nb*8) MDIE("texture slots probe argument ABI");
            MTLRenderPipelineDescriptor *pd=[MTLRenderPipelineDescriptor new]; pd.vertexFunction=[lib newFunctionWithName:@"vs"];pd.fragmentFunction=sh->fn;pd.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;
            pipelines[i]=[g_dev newRenderPipelineStateWithDescriptor:pd error:&error];
            if(!pipelines[i]) MDIE("texture slots probe pipeline: %s",error.localizedDescription.UTF8String);
        }
        for(int mode=0;mode<3;mode++) for(int submission=0;submission<2;submission++) {
            atomic_store(&g_tex_slots_on,mode!=0);atomic_store(&g_tex_slots_check,mode==2);
            atomic_store(&g_arg_epoch_on,0);g_tex_slots_negative=mode?negative:0;
            mtl_sub_begin();mtl_exec((const uint8_t *)&end);
            for(int i=0;i<2;i++){serial_put(textures[i].serial,sources[i]);mtl_reg_tex(51+i,&textures[i],NULL);}
            mtl_reg_samp(61,&clamp);mtl_reg_samp(62,&repeat);
            // Keep sampler objects alive through queued draws even when re-registering their IDs.
            registry_lock();id __attribute__((objc_precise_lifetime)) sampler0=samp_by_id(61),sampler1=samp_by_id(62);registry_unlock();
            uint8_t expected[64*8*4]; int current=0,combined=0,separate=0,unbound=0;
            g_pass.serial++;args_dirty_all();
            MTL4RenderPassDescriptor *rp=[MTL4RenderPassDescriptor new];rp.colorAttachments[0].texture=output;rp.colorAttachments[0].loadAction=MTLLoadActionClear;rp.colorAttachments[0].storeAction=MTLStoreActionStore;rp.renderTargetWidth=64;rp.renderTargetHeight=8;
            id<MTL4RenderCommandEncoder> en=enc_r_begin(rp);enc_r_cull(en,MTLCullModeNone);enc_r_viewport(en,(MTLViewport){0,0,64,8,0,1});
            p_bind_handles tex={.stage=1,.n=1,.h={51|(UINT64_C(61)<<20)}},samp={.stage=1,.n=1,.h={UINT64_C(61)<<20}};
            for(int stripe=0;stripe<16;stripe++) {
                int shader=stripe==2?1:0;
                if(stripe==4){tex.h[0]=52|(UINT64_C(61)<<20);current=1;}
                if(stripe==5){tex.h[0]=52|(UINT64_C(62)<<20);combined=1;}
                if(stripe==6){samp.h[0]=UINT64_C(62)<<20;separate=1;}
                if(stripe==7){mtl_reg_tex(52,&textures[0],NULL);current=0;}
                if(stripe==9){serial_put(textures[0].serial,sources[2]);current=2;}
                if(stripe==10){mtl_reg_samp(62,&clamp);combined=separate=0;}
                if(stripe==11){tex.h[0]=0;unbound=1;}
                if(stripe==12){tex.h[0]=51|(UINT64_C(61)<<20);unbound=0;}
                if(stripe==13){samp.h[0]=0;}
                if(stripe==14){enc_r_end(en);rp.colorAttachments[0].loadAction=MTLLoadActionLoad;en=enc_r_begin(rp);enc_r_cull(en,MTLCullModeNone);enc_r_viewport(en,(MTLViewport){0,0,64,8,0,1});g_pass.serial++;}
                p_bind_program program={&programs[shader],0x1f};state_op(OP_BIND_PROGRAM,&program);
                p_bind_buf u={1,0,(uint64_t)(uintptr_t)mem+16*stripe,16};state_op(OP_BIND_UBO,&u);
                state_op(OP_BIND_TEX,&tex);state_op(OP_BIND_SAMP,&samp);
                uint64_t hits=g_tex_slots_hits;
                enc_r_pso(en,pipelines[shader]);enc_r_scissor(en,(MTLScissorRect){stripe*4,0,4,8});
                encode_args((id<MTLCommandEncoder>)en,shaders[shader],1,0);enc_r_draw(en,MTLPrimitiveTypeTriangle,0,3);
                if(mode && !negative && (stripe==1||stripe==3||stripe==8||stripe==15) && g_tex_slots_hits<=hits) MDIE("texture slots probe did not exercise reuse kind%d stripe%d",kind,stripe);
                if(mode && !negative && (stripe==7||stripe==9||stripe==10||stripe==14) && g_tex_slots_hits!=hits) MDIE("texture slots probe failed invalidation kind%d stripe%d",kind,stripe);
                for(int y=0;y<8;y++)for(int x=stripe*4;x<stripe*4+4;x++) {
                    uint8_t *p=expected+(y*64+x)*4;
                    p[0]=unbound?0:pixels[current][kind==2||combined?0:4];
                    p[1]=unbound?0:pixels[current][kind==2||separate?1:5];
                    p[2]=unbound?0:pixels[current][2];p[3]=stripe&1?191:64;
                }
                checked++;
            }
            enc_r_end(en);enc_b_copy_texture_buffer(blit(),output,0,0,MTLOriginMake(0,0,0),MTLSizeMake(64,8,1),rb,0,256,2048);mtl_sub_commit();mtl_finish();
            for(int i=0;i<2048;i++){if(abs((int)((uint8_t *)rb.contents)[i]-expected[i])>1) MDIE("texture slots probe GPU mismatch kind%d mode%d stripe%d channel%d got%d want%d",kind,mode,(i/4)%64/4,i%4,((uint8_t *)rb.contents)[i],expected[i]);checked++;}
            (void)sampler0;(void)sampler1;
        }
        for(int i=0;i<2;i++){mtl_reg_tex(51+i,NULL,NULL);serial_del(textures[i].serial);}
        for(int i=0;i<3;i++)res_remove(sources[i]);
    }
    if(!g_tex_slots_hits||!g_tex_slots_verified) MDIE("texture slots probe missed cache/shadow paths");
    MLOG("texture slots probe: hits=%llu verified=%llu",(unsigned long long)g_tex_slots_hits,(unsigned long long)g_tex_slots_verified);
    atomic_store(&g_tex_slots_on,0);atomic_store(&g_tex_slots_check,0);g_tex_slots_negative=0;
    memset(&S,0,sizeof S);args_dirty_all();mtl_pool_del(mem);free(mem);res_remove(typed);res_remove(rb);res_remove(output);
    return checked;
}
