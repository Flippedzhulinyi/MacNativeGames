// 着色器反射 json（B：Switch 原版翻译，tools/dmsh_build.py 出）→ 定长 C 数组（nvn_refl.h）
// Shader reflection json (B: produced by translating the original Switch shaders, output of tools/dmsh_build.py) → fixed-length C arrays (nvn_refl.h)
#import "nvn_refl.h"
#import <Metal/Metal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int dynamic_uniform_handle(NSString *name, int sampler, uint16_t *reg, uint16_t *off) {
    if (sampler) {
        if (![name hasSuffix:@"Smplr"]) return 0;
        name = [name substringToIndex:name.length - 5];
    }
    const char *text = name.UTF8String;
    int cbuf_slot = 0, consumed = 0;
    unsigned long long handle = 0;
    if (!text || sscanf(text, "%*[^_]_%*[ti]_cb%d_%llx%n", &cbuf_slot, &handle, &consumed) != 2 || text[consumed] != '\0') return 0;
    if (cbuf_slot < 3 || cbuf_slot > 16 || handle > 0x3fff) return 0;
    *reg = (uint16_t)(cbuf_slot - 3);
    *off = (uint16_t)(handle * 4);
    return 1;
}

// 哑贴图类型：与原 dummy_tex 同一套前缀判定（未绑贴图槽按 D3D 语义读出 0）
// Dummy texture type: same prefix rules as the original dummy_tex (an unbound texture slot reads 0 per D3D semantics)
static void dummy_kind(NSString *t, uint8_t *tt, uint8_t *pf) {
    MTLTextureType y = MTLTextureType2D;
    if ([t hasPrefix:@"texture2d_array"] || [t hasPrefix:@"depth2d_array"]) y = MTLTextureType2DArray;
    else if ([t hasPrefix:@"texturecube_array"] || [t hasPrefix:@"depthcube_array"]) y = MTLTextureTypeCubeArray;
    else if ([t hasPrefix:@"texturecube"] || [t hasPrefix:@"depthcube"]) y = MTLTextureTypeCube;
    else if ([t hasPrefix:@"texture3d"]) y = MTLTextureType3D;
    else if ([t hasPrefix:@"texture1d_array"]) y = MTLTextureType1DArray;
    else if ([t hasPrefix:@"texture1d"]) y = MTLTextureType1D;
    *tt = (uint8_t)y;
    *pf = [t hasPrefix:@"depth"] ? NVN_DPF_DEPTH : [t containsString:@"<uint"] ? NVN_DPF_UINT : [t containsString:@"<int"] ? NVN_DPF_SINT : NVN_DPF_FLOAT;
}

/* TOTK 2026-10-16: the json's rw came from the translator's BufferUsageFlags tested with the wrong bit (& 2; Write is
   1 << 0), so every cached reflection says read-only -- while the deferred-lighting quads (dbe0acd9 ...) store per-tile
   feedback into the stats buffer. The loader (nvn_mtl.m refl_mark_stores) sets rw from the MSL's actual stores / atomics;
   here only the json flag and a write-access image type count. (A non-const `device` pointer is not enough: spirv-cross
   emits it for 1,140 fragment variants that never store, and treating them as writers disables argument-block reuse.) */
static int refl_rw(NSDictionary *b) {
    if ([b[@"rw"] isKindOfClass:[NSNumber class]] && [b[@"rw"] boolValue]) return 1;
    NSString *t = b[@"msl_type"]; if (![t isKindOfClass:[NSString class]]) return 0;
    return [t containsString:@"access::write"] || [t containsString:@"access::read_write"];
}
int nvn_refl_from_json(NSDictionary *j, nvn_refl *o, char *err, int errlen) {
    memset(o, 0, sizeof *o);
    #define FAIL(...) do { snprintf(err, errlen, __VA_ARGS__); return 1; } while (0)
    if (![j[@"route"] isEqual:@"B"]) FAIL("不是 B 反射（route ≠ B；A 路线 / PC 链反射已退役）");
    {   // Switch 原版翻译：种类与 NVN 槽号已由 dmsh_build.py 从 MSL 成员名解出 | Translated original Switch shaders: kind and NVN slot number are already parsed from the MSL member names by dmsh_build.py
        NSArray *bs = j[@"bindings"];
        if (![bs isKindOfClass:[NSArray class]]) FAIL("缺 bindings");
        if (bs.count > NVN_REFL_MAXB) FAIL("绑定 %lu 个，超上限 %d", (unsigned long)bs.count, NVN_REFL_MAXB);
        o->route_b = 1; o->abi = 0;   // spirv-cross 第 0 组 → [[buffer(0)]] | spirv-cross set 0 → [[buffer(0)]]
        for (NSDictionary *b in bs) {
            NSString *k = b[@"kind"]; nvn_rbind *r = &o->b[o->nb];
            id rg = b[@"reg"]; int reg = [rg isKindOfClass:[NSNumber class]] ? [rg intValue] : -1, aid = [b[@"arg_id"] intValue];
            r->aid = (uint16_t)aid; r->reg = reg < 0 ? 0 : (uint16_t)reg;
            if ([k isEqualToString:@"cbuf"]) r->kind = NVN_RB_CBUF;
            else if ([k isEqualToString:@"samp"]) {
                r->kind = NVN_RB_SAMP;
                if (reg < 0) {
                    if (!dynamic_uniform_handle(b[@"msl_name"], 1, &r->reg, &r->off)) FAIL("sampler %s has no supported handle slot", [b[@"msl_name"] UTF8String]);
                    r->kind = NVN_RB_SAMPTU;
                }
            }
            else if ([k isEqualToString:@"samp_tex"]) {
                r->kind = NVN_RB_SAMPT;
                if (reg < 0) {
                    if (!dynamic_uniform_handle(b[@"msl_name"], 1, &r->reg, &r->off)) FAIL("sampler %s has no supported handle slot", [b[@"msl_name"] UTF8String]);
                    r->kind = NVN_RB_SAMPTU;
                }
            }
            else if ([k isEqualToString:@"tex"]) {
                r->kind = NVN_RB_TEX;
                if (reg < 0) {
                    if (!dynamic_uniform_handle(b[@"msl_name"], 0, &r->reg, &r->off)) FAIL("texture %s has no supported handle slot", [b[@"msl_name"] UTF8String]);
                    r->kind = NVN_RB_TEXU;
                }
                dummy_kind(b[@"msl_type"], &r->dtt, &r->dpf);
            }
            else if ([k isEqualToString:@"img"]) {
                r->kind = NVN_RB_IMG; dummy_kind(b[@"msl_type"], &r->dtt, &r->dpf); r->rw = refl_rw(b);
                if (reg < 0) {
                    if (!dynamic_uniform_handle(b[@"msl_name"], 0, &r->reg, &r->off)) FAIL("image %s has no supported handle slot", [b[@"msl_name"] UTF8String]);
                    r->kind = NVN_RB_IMGU;
                }
            }
            else if ([k isEqualToString:@"tbuf"]) {
                r->kind = NVN_RB_TBUF; uint8_t tt; dummy_kind(b[@"msl_type"], &tt, &r->dpf);
                if (reg < 0) {
                    if (!dynamic_uniform_handle(b[@"msl_name"], 0, &r->reg, &r->off)) FAIL("texture buffer %s has no supported handle slot", [b[@"msl_name"] UTF8String]);
                    r->kind = NVN_RB_TBUFU;
                }
            }
            else if ([k isEqualToString:@"sbuf"]) { r->kind = NVN_RB_SBUFP; r->rw = refl_rw(b); }
            else if ([k isEqualToString:@"ubo_ptr"]) r->kind = NVN_RB_UBOP;
            else if ([k isEqualToString:@"sbuf_ubo"]) { r->kind = NVN_RB_SBUFU; r->rw = refl_rw(b); r->off = (uint16_t)[b[@"off"] intValue]; }
            else if ([k isEqualToString:@"support"]) r->kind = NVN_RB_SUPPORT;
            else if ([k isEqualToString:@"c1"]) r->kind = NVN_RB_C1;
            else if ([k isEqualToString:@"drvcb"]) r->kind = [b[@"bank"] intValue] == 2 ? NVN_RB_DRV2 : NVN_RB_DRV0;
            else FAIL("B 绑定种类 %s 未实现（%s）", k.UTF8String, [b[@"msl_name"] UTF8String]);
            if ((r->kind == NVN_RB_CBUF || r->kind == NVN_RB_SAMP || r->kind == NVN_RB_SAMPT || r->kind == NVN_RB_TEX || r->kind == NVN_RB_IMG || r->kind == NVN_RB_TBUF || r->kind == NVN_RB_SBUFP || r->kind == NVN_RB_UBOP || r->kind == NVN_RB_SBUFU) && reg < 0)
                FAIL("B 绑定 %s 没解出槽号", [b[@"msl_name"] UTF8String]);
            o->nb++;
        }
        NSDictionary *dr = j[@"drv_reads"];
        if ([dr isKindOfClass:[NSDictionary class]]) { o->drv_read[0] = dr[@"0"] != nil; o->drv_read[2] = dr[@"2"] != nil; }
        NSArray *uf = j[@"drv_unfillable"];
        if ([uf isKindOfClass:[NSArray class]] && uf.count) FAIL("运行时读驱动段的回放层填不了的位置：%s", [[uf componentsJoinedByString:@" "] UTF8String]);
        NSString *c1 = j[@"c1"];
        if (c1.length % 2 || c1.length / 2 > sizeof o->c1) FAIL("c1 长 %lu 字节，超上限或不成对", (unsigned long)c1.length / 2);
        if (c1.length) { o->has_c1 = 1; o->c1_len = (uint16_t)(c1.length / 2); for (unsigned i = 0; i < o->c1_len; i++) o->c1[i] = (uint8_t)strtoul([[c1 substringWithRange:NSMakeRange(2 * i, 2)] UTF8String], NULL, 16); }
        for (NSDictionary *v in j[@"vertex_inputs"]) {   // [[attribute(n)]]：n 即 NVN 顶点属性号 | [[attribute(n)]]: n is the NVN vertex attribute number
            int loc = [v[@"location"] intValue]; NSString *t = v[@"msl_type"];
            if (loc < 0 || loc >= NVN_REFL_MAXV || o->nv >= NVN_REFL_MAXV) FAIL("B 顶点输入 %d 越界", loc);
            o->v[o->nv].loc = o->v[o->nv].nvn = (uint8_t)loc;
            o->v[o->nv].ct = [t hasPrefix:@"uint"] ? NVN_CT_UINT : [t hasPrefix:@"int"] ? NVN_CT_INT : NVN_CT_FLOAT;
            o->nv++;
        }
        NSDictionary *ra = j[@"raster"];
        o->pos_attr = -1; o->may_discard = 1; o->writes_smask = 1;
        if ([ra isKindOfClass:[NSDictionary class]]) {
            if (ra[@"pos_attr"]) { int pa = [ra[@"pos_attr"] intValue]; o->pos_attr = (int8_t)(pa >= 0 && pa < 16 ? pa : -1); o->pos_w1 = [ra[@"pos_w"] isEqual:@"one"]; }
            if (ra[@"discard"]) o->may_discard = [ra[@"discard"] intValue] != 0;
            if (ra[@"sample_mask"]) o->writes_smask = [ra[@"sample_mask"] intValue] != 0;
            for (NSNumber *c in ra[@"colors"]) if (c.intValue >= 0 && c.intValue < 8) o->color_mask |= (uint8_t)(1u << c.intValue);
        }
        memset(o->uv_attr, -1, sizeof o->uv_attr); memset(o->uv_aff_attr, -1, sizeof o->uv_aff_attr);
        NSDictionary *ua = [ra isKindOfClass:[NSDictionary class]] ? ra[@"uv_affine"] : nil;
        if ([ua isKindOfClass:[NSDictionary class]]) for (NSString *k in ua) { int l = k.intValue; NSDictionary *e = ua[k]; int a = [e[@"attr"] intValue];
            if (l < 0 || l >= 32 || a < 0 || a >= 16) continue;
            NSArray *refs[4] = {e[@"sx"], e[@"ox"], e[@"sy"], e[@"oy"]}; int ok = 1;
            for (int q = 0; q < 4; q++) { NSArray *r = refs[q]; if (![r isKindOfClass:[NSArray class]] || r.count != 3) { ok = 0; break; }
                int sl = [r[0] intValue], vec = [r[1] intValue], cmp = [r[2] intValue]; if (sl < 0 || sl > 15 || vec < 0 || vec > 63 || cmp < 0 || cmp > 3) { ok = 0; break; }
                o->uv_aff[l][q] = (uint16_t)(sl << 8 | vec << 2 | cmp); }
            if (ok) o->uv_aff_attr[l] = (int8_t)a; }
        NSDictionary *uv = [ra isKindOfClass:[NSDictionary class]] ? ra[@"uv_from_attr"] : nil;
        if ([uv isKindOfClass:[NSDictionary class]]) for (NSString *k in uv) { int l = k.intValue, a = [uv[k] intValue]; if (l >= 0 && l < 32 && a >= 0 && a < 16) o->uv_attr[l] = (int8_t)a; }
        NSDictionary *fe = j[@"fetch"];
        if ([fe isKindOfClass:[NSDictionary class]]) {
            for (NSDictionary *c in fe[@"calls"]) { int i = [c[@"fc"] intValue], r = [c[@"tex_reg"] intValue], l = [c[@"varying_locn"] intValue];
                if (i != o->nfc || i >= 32 || r < 0 || r >= 128 || l < 0 || l >= 32) FAIL("fetch 调用表不连续或越界（第 %d 条）", i);
                o->fc_reg[o->nfc] = (uint8_t)r; o->fc_locn[o->nfc] = (uint8_t)l; o->nfc++; }
            for (NSNumber *r in fe[@"mixed_regs"]) if (r.intValue >= 0 && r.intValue < 128) o->fc_mixed[r.intValue >> 6] |= 1ull << (r.intValue & 63);
            for (NSDictionary *u in fe[@"outputs"]) { if (o->nfo >= 4) FAIL("fetch 输出超过 4 个"); o->fo_color[o->nfo++] = (uint8_t)[u[@"color"] intValue]; }
        }
        NSArray *tg = j[@"threadgroup_size"];
        if ([tg isKindOfClass:[NSArray class]] && tg.count == 3) for (int i = 0; i < 3; i++) o->tg[i] = (uint16_t)[tg[i] intValue];
        return 0;
    }
    #undef FAIL
}

int nvn_refl_probe_dynamic_uniform_handle(void) {
    NSDictionary *j = @{
        @"route": @"B",
        @"bindings": @[
            @{@"kind": @"tex", @"reg": NSNull.null, @"arg_id": @1, @"msl_name": @"fp_t_cb3_0", @"msl_type": @"texture2d<float>"},
            @{@"kind": @"samp_tex", @"reg": NSNull.null, @"arg_id": @2, @"msl_name": @"fp_t_cb3_0Smplr", @"msl_type": @"sampler"},
            @{@"kind": @"img", @"reg": NSNull.null, @"arg_id": @3, @"msl_name": @"fp_i_cb4_8", @"msl_type": @"texture2d<float, access::write>", @"rw": @YES},
            @{@"kind": @"tbuf", @"reg": NSNull.null, @"arg_id": @4, @"msl_name": @"fp_t_cb4_8", @"msl_type": @"texture_buffer<float>"},
            @{@"kind": @"samp", @"reg": NSNull.null, @"arg_id": @5, @"msl_name": @"fp_t_cb4_8Smplr", @"msl_type": @"sampler"},
        ],
    };
    nvn_refl out = {0}; char err[128];
    if (nvn_refl_from_json(j, &out, err, sizeof err)) return 1;
    if (out.nb != 5 || out.b[0].kind != NVN_RB_TEXU || out.b[0].reg != 0 || out.b[0].off != 0 ||
        out.b[1].kind != NVN_RB_SAMPTU || out.b[1].reg != 0 || out.b[1].off != 0 ||
        out.b[2].kind != NVN_RB_IMGU || out.b[2].reg != 1 || out.b[2].off != 32 || !out.b[2].rw ||
        out.b[3].kind != NVN_RB_TBUFU || out.b[3].reg != 1 || out.b[3].off != 32 ||
        out.b[4].kind != NVN_RB_SAMPTU || out.b[4].reg != 1 || out.b[4].off != 32) return 1;
    NSDictionary *bad = @{@"route": @"B", @"bindings": @[@{@"kind": @"img", @"reg": NSNull.null, @"arg_id": @1, @"msl_name": @"fp_i_cb2_0", @"msl_type": @"texture2d<float, access::write>"}]};
    return nvn_refl_from_json(bad, &out, err, sizeof err) == 0;
}
