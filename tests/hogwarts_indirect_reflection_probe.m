#import <Foundation/Foundation.h>
#include "nvn_refl.h"
#include <stdio.h>
#include <string.h>

static int parse(NSArray *bindings, nvn_refl *out, char *error, size_t error_size) {
    return nvn_refl_from_json(@{@"route": @"B", @"bindings": bindings}, out, error, (int)error_size);
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        NSDictionary *tex = @{@"kind": @"tex", @"arg_id": @12,
            @"msl_name": @"fp_t3d_cb196613_10578000",
            @"msl_type": @"array<texture3d<float>, 32>"};
        NSDictionary *samp = @{@"kind": @"samp", @"arg_id": @44, @"reg": @2,
            @"msl_name": @"fp_t3d_cb196613_10578000Smplr",
            @"msl_type": @"array<sampler, 32>"};
        NSArray *bindings = @[tex, samp];
        if (argc > 1) {
            NSData *data = [NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[1]]];
            NSError *readError = nil;
            id decoded = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:&readError] : nil;
            if (![decoded isKindOfClass:[NSDictionary class]] ||
                ![decoded[@"bindings"] isKindOfClass:[NSArray class]]) {
                fprintf(stderr, "cannot load reflection: %s\n", readError.localizedDescription.UTF8String ?: "missing file");
                return 3;
            }
            bindings = decoded[@"bindings"];
        }
        nvn_refl out;
        char error[256] = {0};
        int parse_result = parse(bindings, &out, error, sizeof error);
#ifdef HOGWARTS_EXPERIMENTAL
        if (getenv("HOGWARTS_EXPECT_DIAGNOSTIC_2D_ARRAY")) {
            if (!parse_result || !strstr(error, "unsupported")) return 55;
            if (nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": bindings},
                                                     &out, error, sizeof error)) {
                fprintf(stderr, "2D array diagnostic reflection rejected: %s\n", error);
                return 56;
            }
            int textures = 0, samplers = 0;
            for (int i = 0; i < out.nb; i++) {
                const nvn_rbind *b = &out.b[i];
                if (b->ptr != 4) continue;
                if (!b->indirect_count || b->indirect_count > 32) return 57;
                textures += b->kind == NVN_RB_ITEX;
                samplers += b->kind == NVN_RB_ISAMP;
            }
            if (!textures || textures != samplers) return 58;
            return 0;
        }
        if (getenv("HOGWARTS_EXPECT_DIAGNOSTIC_CUBE")) {
            if (!parse_result || !strstr(error, "unsupported")) return 44;
            if (nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": bindings},
                                                     &out, error, sizeof error)) {
                fprintf(stderr, "cube diagnostic reflection rejected: %s\n", error);
                return 45;
            }
            int cube_tex = 0, cube_samp = 0;
            for (int i = 0; i < out.nb; i++) {
                nvn_rbind *b = &out.b[i];
                if (b->ptr != 3) continue;
                if (b->reg != 6 || b->off != 7 || b->indirect_count != 32) return 46;
                cube_tex += b->kind == NVN_RB_ITEX;
                cube_samp += b->kind == NVN_RB_ISAMP;
            }
            if (cube_tex != 1 || cube_samp != 1) return 47;
            return 0;
        }
        if (getenv("HOGWARTS_EXPECT_UNSUPPORTED_2D")) {
            if (!parse_result || !strstr(error, "indirect uniform texture")) {
                fprintf(stderr, "expected unsupported indirect uniform texture; got: %s\n", error);
                return 33;
            }
            int seen = 0;
            for (NSDictionary *binding in bindings) {
                NSString *name = binding[@"msl_name"];
                if (![name isKindOfClass:[NSString class]] ||
                    ![name hasPrefix:@"fp_t_cb393218_10028166"]) continue;
                memset(error, 0, sizeof error);
                if (!parse(@[binding], &out, error, sizeof error) ||
                    !strstr(error, "indirect uniform sampler")) return 36;
                seen++;
            }
            if (seen != 2) return 37;
            memset(error, 0, sizeof error);
            if (nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": bindings},
                                                     &out, error, sizeof error)) {
                fprintf(stderr, "scalar diagnostic reflection rejected: %s\n", error);
                return 38;
            }
            int textures = 0, samplers = 0, reversed = 0;
            for (int i = 0; i < out.nb; i++) {
                const nvn_rbind *b = &out.b[i];
                if (b->kind == NVN_RB_SCALAR_ITEX) {
                    textures++;
                    if (b->ptr == 2) {
                        if (b->reg != 2 || b->off != 0x28 || b->indirect_count != 6) return 51;
                        reversed++;
                    }
                }
                if (b->kind == NVN_RB_SCALAR_ISAMP) samplers++;
            }
            if (textures != 8 || samplers != 8 || reversed != 1 || !out.has_indirect_textures) return 39;
            return 0;
        }
#endif
        if (parse_result) {
            fprintf(stderr, "valid reflection rejected: %s\n", error); return 1;
        }
        int seen_tex = 0, seen_samp = 0;
        for (int i = 0; i < out.nb; i++) {
            nvn_rbind *b = &out.b[i];
            if (b->kind != NVN_RB_ITEX && b->kind != NVN_RB_ISAMP) continue;
            if (b->reg != 2 || b->off != 2 || b->indirect_count != 32 ||
                b->aid != (b->kind == NVN_RB_ITEX ? 12 : 44)) return 2;
            seen_tex += b->kind == NVN_RB_ITEX;
            seen_samp += b->kind == NVN_RB_ISAMP;
        }
        if (seen_tex != 1 || seen_samp != 1 || !out.has_indirect_textures) return 4;
        if (nvn_refl_argument_slots(&out) < 76) return 16;
        if (argc > 1) {
            const uint8_t expected[] = {NVN_RB_SUPPORT, NVN_RB_CBUF, NVN_RB_CBUF, NVN_RB_CBUF,
                NVN_RB_C1, NVN_RB_SBUFP, NVN_RB_TEX, NVN_RB_SAMP, NVN_RB_TBUF,
                NVN_RB_TEX, NVN_RB_SAMP, NVN_RB_TBUF, NVN_RB_ITEX, NVN_RB_ISAMP};
            const uint16_t aids[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 44};
            const uint16_t regs[] = {0, 3, 0, 1, 0, 0, 0, 0, 3, 1, 1, 2, 2, 2};
            if (out.nb != 14 || nvn_refl_argument_slots(&out) != 76) return 23;
            for (unsigned i = 0; i < 14; i++) {
                int found = 0;
                for (int j = 0; j < out.nb; j++) {
                    if (out.b[j].aid != aids[i]) continue;
                    if (out.b[j].kind != expected[i] || out.b[j].reg != regs[i]) return 24;
                    found++;
                }
                if (found != 1) return 25;
            }
            return 0;
        }
        if (nvn_refl_argument_slots(&out) != 76) return 16;

        nvn_refl direct = {0};
        direct.nb = 2;
        direct.b[0] = (nvn_rbind){.kind = NVN_RB_CBUF, .aid = 9};
        direct.b[1] = (nvn_rbind){.kind = NVN_RB_TEX, .aid = 3};
        if (nvn_refl_argument_slots(&direct) != 10) return 17;
        direct.b[1] = (nvn_rbind){.kind = NVN_RB_ITEX, .aid = 127, .indirect_count = 2};
        if (nvn_refl_argument_slots(&direct) != -1) return 18;
        direct.b[1].indirect_count = 1;
        if (nvn_refl_argument_slots(&direct) != 128) return 19;
        direct.b[1].indirect_count = 0;
        if (nvn_refl_argument_slots(&direct) != -1) return 20;
        direct.b[1].aid = 0; direct.b[1].indirect_count = 33;
        if (nvn_refl_argument_slots(&direct) != -1) return 21;
        direct.nb = NVN_REFL_MAXB + 1;
        if (nvn_refl_argument_slots(&direct) != -1) return 22;

        NSMutableDictionary *bad = [samp mutableCopy];
        bad[@"arg_id"] = @43;
        if (!parse(@[tex, bad], &out, error, sizeof error) || !strstr(error, "overlapping")) return 5;
        bad[@"arg_id"] = @97;
        if (!parse(@[tex, bad], &out, error, sizeof error) || !strstr(error, "range invalid")) return 6;
        bad[@"arg_id"] = @44; bad[@"reg"] = @3;
        if (!parse(@[tex, bad], &out, error, sizeof error) || !strstr(error, "inconsistent")) return 7;
        bad[@"reg"] = @2; bad[@"msl_type"] = @"array<sampler, 31>";
        if (!parse(@[tex, bad], &out, error, sizeof error) || !strstr(error, "mismatched pair")) return 8;
        if (!parse(@[tex], &out, error, sizeof error) || !strstr(error, "mismatched pair")) return 9;
        bad[@"msl_type"] = @"array<sampler, 32>"; bad[@"arg_id"] = @(-1);
        if (!parse(@[tex, bad], &out, error, sizeof error) || !strstr(error, "range invalid")) return 10;
        bad[@"arg_id"] = @44; bad[@"kind"] = @"tex";
        if (!parse(@[tex, bad], &out, error, sizeof error) || !strstr(error, "inconsistent")) return 11;
        NSDictionary *overlap = @{@"kind": @"cbuf", @"arg_id": @13, @"reg": @0};
        if (!parse(@[tex, samp, overlap], &out, error, sizeof error) || !strstr(error, "overlapping")) return 12;
        bad[@"kind"] = @"samp"; bad[@"reg"] = @2.5;
        if (!parse(@[tex, bad], &out, error, sizeof error) || !strstr(error, "inconsistent")) return 13;
        bad[@"reg"] = @2; bad[@"msl_type"] = @"array<sampler, 33>";
        if (!parse(@[bad], &out, error, sizeof error) || !strstr(error, "unsupported")) return 14;
        bad[@"msl_type"] = @"array<sampler, 32>"; bad[@"reg"] = @"2";
        if (!parse(@[tex, bad], &out, error, sizeof error) || !strstr(error, "inconsistent")) return 15;
#ifdef HOGWARTS_EXPERIMENTAL
        NSDictionary *unsupported = @{@"kind": @"tex", @"arg_id": @0, @"reg": @0,
            @"msl_name": @"fp_t2d_cb196613_10578000", @"msl_type": @"array<texture2d<float>, 32>"};
        if (!parse(@[unsupported], &out, error, sizeof error) || !strstr(error, "unsupported")) return 26;
        unsupported = @{@"kind": @"samp", @"arg_id": @0, @"reg": @0,
            @"msl_name": @"fp_t2d_cb196613_10578000Smplr", @"msl_type": @"array<sampler, 32>"};
        if (!parse(@[unsupported], &out, error, sizeof error) || !strstr(error, "unsupported")) return 27;
        unsupported = @{@"kind": @"tex", @"arg_id": @0, @"reg": @0,
            @"msl_name": @"fp_t2d_cb0_0", @"msl_type": @"array<depth2d<float>, 2>"};
        if (!parse(@[unsupported], &out, error, sizeof error) || !strstr(error, "unsupported")) return 28;
        NSDictionary *ordinary = @{@"kind": @"tex", @"arg_id": @0, @"reg": @0,
            @"msl_name": @"fp_t2d_cb0_0", @"msl_type": @"texture2d<float>"};
        if (parse(@[ordinary], &out, error, sizeof error) || out.b[0].kind != NVN_RB_TEX) return 29;
        NSDictionary *single = @{@"kind": @"tex", @"arg_id": @0, @"reg": [NSNull null],
            @"msl_name": @"fp_t_cb196613_10568000", @"msl_type": @"texture2d<float>"};
        if (!parse(@[single], &out, error, sizeof error) || !strstr(error, "indirect uniform texture")) return 31;
        single = @{@"kind": @"samp", @"arg_id": @0, @"reg": @0,
            @"msl_name": @"fp_t_cb196613_10568000Smplr", @"msl_type": @"sampler"};
        if (!parse(@[single], &out, error, sizeof error) || !strstr(error, "indirect uniform texture")) return 32;
        single = @{@"kind": @"tex", @"arg_id": @0, @"reg": @1,
            @"msl_name": @"fp_t_cb393218_10028166", @"msl_type": @"texture2d<float>"};
        if (!parse(@[single], &out, error, sizeof error) || !strstr(error, "indirect uniform sampler")) return 34;
        single = @{@"kind": @"samp", @"arg_id": @0, @"reg": [NSNull null],
            @"msl_name": @"fp_t_cb393218_10028166Smplr", @"msl_type": @"sampler"};
        if (!parse(@[single], &out, error, sizeof error) || !strstr(error, "indirect uniform sampler")) return 35;
        NSDictionary *s_tex = @{@"kind": @"tex", @"arg_id": @4, @"reg": [NSNull null],
            @"msl_name": @"fp_t_cb196613_10570002", @"msl_type": @"texture2d<float>"};
        NSDictionary *s_samp = @{@"kind": @"samp", @"arg_id": @5, @"reg": @1,
            @"msl_name": @"fp_t_cb196613_10570002Smplr", @"msl_type": @"sampler"};
        NSDictionary *s_json = @{@"route": @"B", @"bindings": @[s_tex, s_samp]};
        if (nvn_refl_from_json_scalar_diagnostic(s_json, &out, error, sizeof error) ||
            out.nb != 2 || !out.has_indirect_textures ||
            out.b[0].kind != NVN_RB_SCALAR_ITEX || out.b[1].kind != NVN_RB_SCALAR_ISAMP ||
            out.b[0].reg != 2 || out.b[0].off != 8 || out.b[0].indirect_count != 1 || out.b[0].ptr != 1 ||
            out.b[0].pair_aid != 5 || out.b[1].pair_aid != 4)
            return 40;
        if (!nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": @[s_tex]},
                                                  &out, error, sizeof error)) return 41;
        NSMutableDictionary *bad_scalar = [s_samp mutableCopy];
        bad_scalar[@"reg"] = @2;
        if (!nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": @[s_tex, bad_scalar]},
                                                  &out, error, sizeof error)) return 42;
        bad_scalar[@"reg"] = @1; bad_scalar[@"arg_id"] = @4;
        if (!nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": @[s_tex, bad_scalar]},
                                                  &out, error, sizeof error)) return 43;
        NSDictionary *cube = @{@"kind": @"tex", @"arg_id": @0, @"reg": [NSNull null],
            @"msl_name": @"fp_tcube_cb196617_105A0000", @"msl_type": @"array<texturecube<float>, 32>"};
        NSDictionary *cube_sampler = @{@"kind": @"samp", @"arg_id": @32, @"reg": @7,
            @"msl_name": @"fp_tcube_cb196617_105A0000Smplr", @"msl_type": @"array<sampler, 32>"};
        if (parse(@[cube, cube_sampler], &out, error, sizeof error) == 0) return 48;
        if (nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": @[cube, cube_sampler]},
                                                 &out, error, sizeof error) ||
            out.b[0].ptr != 3 || out.b[1].ptr != 3 || nvn_refl_argument_slots(&out) != 64) return 49;
        if (!nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": @[cube]},
                                                  &out, error, sizeof error)) return 50;
        NSDictionary *array2d = @{@"kind": @"tex", @"arg_id": @0, @"reg": [NSNull null],
            @"msl_name": @"fp_t2d_cb196615_10570000", @"msl_type": @"array<texture2d<float>, 32>"};
        NSDictionary *array2d_sampler = @{@"kind": @"samp", @"arg_id": @32, @"reg": @1,
            @"msl_name": @"fp_t2d_cb196615_10570000Smplr", @"msl_type": @"array<sampler, 32>"};
        if (!parse(@[array2d, array2d_sampler], &out, error, sizeof error)) return 52;
        if (nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": @[array2d, array2d_sampler]},
                                                 &out, error, sizeof error) ||
            out.b[0].ptr != 4 || out.b[1].ptr != 4 || out.b[0].reg != 4 ||
            out.b[0].off != 1 || out.b[0].pair_aid != 32 || out.b[1].pair_aid != 0 ||
            nvn_refl_argument_slots(&out) != 64) return 53;
        if (!nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": @[array2d]},
                                                  &out, error, sizeof error) ||
            !nvn_refl_from_json_scalar_diagnostic(@{@"route": @"B", @"bindings": @[array2d, cube_sampler]},
                                                  &out, error, sizeof error)) return 54;
#else
        NSDictionary *legacy = @{@"kind": @"tex", @"arg_id": @0, @"reg": @0,
            @"msl_name": @"fp_t2d_cb196613_10578000", @"msl_type": @"array<texture2d<float>, 32>"};
        if (parse(@[legacy], &out, error, sizeof error) || out.b[0].kind != NVN_RB_TEX) return 30;
#endif
        return 0;
    }
}
