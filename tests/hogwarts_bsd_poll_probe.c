#include "ipc.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void runtime_hogwarts_bsd_poll(const IpcRequest *, IpcResponse *);
_Noreturn void runtime_fail(const char *message) { fprintf(stderr, "%s\n", message); exit(2); }
const void *ipc_arg(const IpcRequest *rq, uint32_t offset, uint32_t size) {
    if (offset > rq->data_size || size > rq->data_size - offset) runtime_fail("invalid argument");
    return rq->data + offset;
}
void *ipc_guest(uint64_t addr, uint64_t size) { (void)size; return (void *)(uintptr_t)addr; }
void ipc_out(IpcResponse *rs, const void *value, uint32_t size) {
    memcpy(rs->data + rs->data_size, value, size); rs->data_size += size;
}
typedef struct { int32_t fd; int16_t events, revents; } Fd;
int main(int argc, char **argv) {
    struct { uint32_t n; int32_t timeout; } args = {3, 0};
    Fd in[3] = {{-1, 1, 7}, {4, 1, 0}, {-2, 1, 7}}, out[3] = {0};
    IpcRequest rq = {.data = (const uint8_t *)&args, .data_size = sizeof(args), .nx = 1, .nc = 1};
    IpcResponse rs = {0};
    rq.x[0] = (IpcBuffer){(uintptr_t)in, sizeof(in), 0};
    rq.c[0] = (IpcBuffer){(uintptr_t)out, sizeof(out), 0};
    if (argc > 1 && !strcmp(argv[1], "short")) rq.x[0].size = sizeof(in) - 1;
    if (argc > 1 && !strcmp(argv[1], "wait")) { args.n = 0; args.timeout = 70; }
    runtime_hogwarts_bsd_poll(&rq, &rs);
    if (argc > 1 && !strcmp(argv[1], "wait")) return 0;
    int32_t result; uint32_t error;
    memcpy(&result, rs.data, 4); memcpy(&error, rs.data + 4, 4);
    if (result != 1 || error || out[0].revents || out[1].revents != 0x20 || out[2].revents ||
        rs.nxout != 1 || rs.xout[0].size != sizeof(out)) return 3;
    args.n = 0; memset(&rs, 0, sizeof(rs));
    runtime_hogwarts_bsd_poll(&rq, &rs);
    memcpy(&result, rs.data, 4);
    if (result || rs.data_size != 8 || rs.nxout) return 4;
    return 0;
}
