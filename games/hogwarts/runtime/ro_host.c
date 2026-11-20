/* Experimental nn::ro host: initialization is local; NRO loading is not implemented. */
#include "runtime.h"
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static atomic_int initialized;

static uint32_t ro_initialize(void) {
    atomic_store(&initialized, 1);
    fprintf(stderr, "[hogwarts] nn::ro initialized locally; dynamic NRO loading is not implemented\n");
    return 0;
}

static uint32_t ro_register(void *info, const void *nrr) {
    (void)info;
    (void)nrr;
    fprintf(stderr, "[hogwarts] nn::ro registration unavailable%s\n",
            atomic_load(&initialized) ? "" : " (not initialized)");
    return 22 | (1 << 9);
}

static uint32_t ro_lookup_symbol(uintptr_t *out, const char *name) {
    if (!out || !name || !*name) {
        fprintf(stderr, "[hogwarts] nn::ro symbol lookup: invalid arguments\n");
        return 22 | (1 << 9);
    }
    void *symbol = runtime_symbol(name);
    if (!symbol) {
        fprintf(stderr, "[hogwarts] nn::ro symbol lookup failed: %s\n", name);
        return 22 | (1 << 9);
    }
    *out = (uintptr_t)symbol;
    return 0;
}

static void ro_unload(void *module) {
    (void)module;
    runtime_fail("nn::ro unload is not implemented");
}

void *runtime_hogwarts_ro_override(const char *name) {
    if (!strcmp(name, "_ZN2nn2ro10InitializeEv")) return ro_initialize;
    if (!strcmp(name, "_ZN2nn2ro18RegisterModuleInfoEPNS0_16RegistrationInfoEPKv")) return ro_register;
    if (!strcmp(name, "_ZN2nn2ro12LookupSymbolEPmPKc")) return ro_lookup_symbol;
    if (!strcmp(name, "_ZN2nn2ro12UnloadModuleEPNS0_6ModuleE")) return ro_unload;
    return NULL;
}
