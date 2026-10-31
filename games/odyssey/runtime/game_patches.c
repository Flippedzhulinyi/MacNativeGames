#include "game_patches.h"
#include <libkern/OSCacheControl.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { ASPECT_DATA_SLOT = 56, ASPECT_STUB_SIZE = 32 };
static _Atomic(uint32_t) *aspect_slot;

static uint32_t aspect_branch(uint64_t from, uint64_t to) {
    int64_t delta = (int64_t)to - (int64_t)from;
    if ((delta & 3) || delta < -(1 << 27) || delta >= (1 << 27)) return 0;
    return 0x14000000u | ((uint32_t)(delta >> 2) & 0x03ffffffu);
}

static uint32_t aspect_adrp(unsigned reg, uint64_t at, uint64_t target) {
    int64_t pages = (int64_t)(target >> 12) - (int64_t)(at >> 12);
    if (pages < -(1 << 20) || pages >= (1 << 20)) return 0;
    uint32_t imm = (uint32_t)pages & 0x1fffff;
    return 0x90000000u | ((imm & 3) << 29) | ((imm >> 2) << 5) | reg;
}

static void patch_aspect(Module *m) {
    static const uint64_t sites[] = {0x6fec9c, 0x6ff578, 0x707f48, 0x77fbb4, 0x7948bc, 0x797ffc};
    const uint32_t original = 0xbd4d9503; /* ldr s3, [x8, #0xd94] (the 1.4.1 16:9 projection ratio) */
    uint64_t stub_off = m->text_end;
    uint64_t text_end = (m->text_end + 0x3fff) & ~0x3fffULL;
    uint64_t data_off = (m->file_size + 0x3fff) & ~0x3fffULL;
    if ((stub_off & 3) || stub_off + ASPECT_STUB_SIZE * (sizeof sites / sizeof *sites) > text_end ||
        data_off + ASPECT_DATA_SLOT + sizeof(uint32_t) > m->size)
        runtime_fail("Odyssey aspect patch layout");
    for (unsigned i = 0; i < ASPECT_STUB_SIZE * (sizeof sites / sizeof *sites); i++)
        if (m->base[stub_off + i]) runtime_fail("Odyssey aspect patch text padding in use");
    for (unsigned i = 0; i < sizeof sites / sizeof *sites; i++) {
        uint32_t ins;
        memcpy(&ins, m->base + sites[i], sizeof ins);
        if (ins != original) {
            fprintf(stderr, "[odyssey] aspect patch main+%#llx: found %08x, expected %08x\n",
                    (unsigned long long)sites[i], ins, original);
            runtime_fail("Odyssey aspect patch does not match game version 1.4.1");
        }
        uint64_t stub = stub_off + ASPECT_STUB_SIZE * i;
        uint32_t adrp = aspect_adrp(10, stub + 8, data_off);
        uint32_t back = aspect_branch(stub + 28, sites[i] + 4);
        if (!adrp || !back) runtime_fail("Odyssey aspect patch branch out of range");
        uint32_t code[8] = {
            ins,
            0xf81f0fea, /* str x10, [sp, #-16]! */
            adrp,
            0xb9400000u | ((ASPECT_DATA_SLOT / 4) << 10) | (10 << 5) | 10, /* ldr w10, [x10, #slot] */
            0x3400004a, /* cbz w10, +8: keep the game's aspect ratio */
            0x1e270000u | (10 << 5) | 3, /* fmov s3, w10 */
            0xf84107ea, /* ldr x10, [sp], #16 */
            back
        };
        memcpy(m->base + stub, code, sizeof code);
        uint32_t jump = aspect_branch(sites[i], stub);
        if (!jump) runtime_fail("Odyssey aspect patch site branch out of range");
        memcpy(m->base + sites[i], &jump, sizeof jump);
        sys_icache_invalidate(m->base + stub, sizeof code);
        sys_icache_invalidate(m->base + sites[i], sizeof jump);
    }
    aspect_slot = (_Atomic(uint32_t) *)(void *)(m->base + data_off + ASPECT_DATA_SLOT);
    atomic_store(aspect_slot, 0);
    fprintf(stderr, "[odyssey] key 4 aspect patch: 6 camera sites, 16:9 <-> 21:9\n");
}

/* Bayonetta 3: the player's 1.2.0 exefs patches (60 fps, 900p, LOD, film grain), applied to main after relocation and
   before its text is sealed. scripts/prepare_patches.py turns each .pchtxt into patches/<slug>.tsv ("offset new orig",
   hex), already checked against the original image and the rewrite; here every site is checked again against the loaded
   bytes, and a mismatch stops the start (a wrong version or a rewritten word must never be patched).
   BY3_PATCHES=<slug>,<slug>,... picks them (the launcher sets it from the settings; unset or empty: none). */
static int hexbytes(const char *s, uint8_t *out, size_t cap, size_t *n) {
    size_t k = 0;
    for (; s[0] && s[1] && s[0] != '\t' && s[0] != '\n'; s += 2) {
        unsigned v; if (k == cap || sscanf(s, "%2x", &v) != 1) return 0;
        out[k++] = (uint8_t)v;
    }
    *n = k; return k > 0;
}
static void apply_file(Module *m, const char *slug) {
    char path[512]; snprintf(path, sizeof path, "patches/%s.tsv", slug);
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "[by3] patch %s: %s missing (scripts/prepare_patches.py)\n", slug, path); runtime_fail("game patch table missing"); }
    char line[4096]; unsigned applied = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == '\n') continue;
        uint64_t off = strtoull(line, NULL, 0); char *a = strchr(line, '\t'), *b = a ? strchr(a + 1, '\t') : NULL;
        uint8_t now[1024], was[1024]; size_t nn, nw;
        if (!a || !b || !hexbytes(a + 1, now, sizeof now, &nn) || !hexbytes(b + 1, was, sizeof was, &nw) || nn != nw)
            runtime_fail("malformed game patch table");
        if (off + nn > m->text_end && off < m->ro_off) runtime_fail("game patch in the rewrite area");
        if (off + nn > m->file_size) runtime_fail("game patch beyond main");
        if (memcmp(m->base + off, was, nw)) { fprintf(stderr, "[by3] patch %s at main+%#llx: original bytes differ\n", slug, (unsigned long long)off); runtime_fail("game patch does not match this game version"); }
        memcpy(m->base + off, now, nn); sys_icache_invalidate(m->base + off, nn); applied++;
    }
    fclose(f);
    fprintf(stderr, "[by3] game patch %s: %u sites\n", slug, applied);
}
void runtime_game_patches(Module *main_module) {
    patch_aspect(main_module);
    const char *list = getenv("BY3_PATCHES");
    if (!list || !*list) { fprintf(stderr, "[by3] game patches: none (BY3_PATCHES)\n"); return; }
    char buf[1024]; snprintf(buf, sizeof buf, "%s", list);
    for (char *save = NULL, *s = strtok_r(buf, ",", &save); s; s = strtok_r(NULL, ",", &save)) {
        for (const char *c = s; *c; c++) if (!((*c >= 'a' && *c <= 'z') || (*c >= '0' && *c <= '9') || *c == '-')) runtime_fail("BY3_PATCHES: bad patch name");
        apply_file(main_module, s);
    }
}

/* Odyssey 1.4.1 uses checked camera-aspect sites; the output resolution remains at the game's native size. */
void runtime_frame_step_pin(double ms) { (void)ms; }
void runtime_frame_step_update(uint64_t now_ns) { (void)now_ns; }
int runtime_output_res(unsigned *w, unsigned *h) { (void)w; (void)h; return 0; }
uint64_t runtime_output_res_extra_bytes(void) { return 0; }
uint64_t runtime_output_size_current(void) { return (uint64_t)1080 << 32 | 1920; }
int runtime_output_res_toggle(void) { return 0; }
int runtime_output_mode_cycle(void) {
    extern int mfxup_output_enabled(void);
    extern void dm_gfx_set_flag(const char *name, int value);
    int enabled = mfxup_output_enabled();
    int next = !enabled;
    dm_gfx_set_flag("mfx_output", next);
    fprintf(stderr, "[totk] key 3: %s\n", next ? "MetalFX 出图放大" : "关闭");
    return 1;
}
int runtime_aspect_toggle(void) {
    if (!aspect_slot) return 0;
    uint32_t current = atomic_load(aspect_slot), next;
    float wide = 21.0f / 9.0f;
    memcpy(&next, &wide, sizeof next);
    if (current == next) next = 0;
    atomic_store(aspect_slot, next);
    fprintf(stderr, "[odyssey] key 4: %s\n", next ? "21:9 宽屏" : "16:9");
    return 1;
}
float runtime_aspect_now(void) {
    if (!aspect_slot) return 0;
    uint32_t bits = atomic_load(aspect_slot);
    float aspect;
    memcpy(&aspect, &bits, sizeof aspect);
    return aspect;
}
