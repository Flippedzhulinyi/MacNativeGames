#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../games/hogwarts/runtime/fs_proxy.c"

_Noreturn void runtime_fail(const char *message) { fprintf(stderr, "%s\n", message); exit(2); }
_Noreturn void ipc_unimplemented(const IpcSession *s, const IpcRequest *rq) {
    (void)s;
    (void)rq;
    exit(3);
}
void runtime_ipc_register(const char *name, IpcHandler handler, IpcOpen open, void (*close)(void *)) {
    (void)name;
    (void)handler;
    (void)open;
    (void)close;
}
void ipc_out(IpcResponse *rs, const void *p, uint32_t n) {
    memcpy(rs->data, p, n);
    rs->data_size = n;
}
int main(int argc, char **argv) {
    Proxy *p = proxy_open();
    IpcSession session = {.state = p};
    IpcRequest rq = {.cmd = 1, .has_pid = 1, .pid = 42, .data_size = 8};
    IpcResponse rs = {0};
    if (argc > 1 && !strcmp(argv[1], "bad-pid")) rq.has_pid = 0;
    if (argc > 1 && !strcmp(argv[1], "before-init")) rq.cmd = 1005;
    proxy_handler(&session, &rq, &rs);
    if (!p->initialized || p->pid != 42) return 4;
    rq.cmd = argc > 1 && !strcmp(argv[1], "unknown") ? 777 : 1005;
    proxy_handler(&session, &rq, &rs);
    uint32_t mode = 1;
    if (rs.data_size != sizeof mode) return 5;
    memcpy(&mode, rs.data, sizeof mode);
    free(p);
    return mode != 0;
}
