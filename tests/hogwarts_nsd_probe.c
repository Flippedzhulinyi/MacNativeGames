#include <stdlib.h>
#include <string.h>
#include "../games/hogwarts/runtime/nsd_service.c"

_Noreturn void ipc_unimplemented(const IpcSession *s, const IpcRequest *rq) {
    (void)s; (void)rq; exit(3);
}
void runtime_ipc_register(const char *name, IpcHandler handler, IpcOpen open, void (*close)(void *)) {
    if (strcmp(name, "nsd:u") || handler != nsd_handler || open || close) exit(4);
}
void ipc_out(IpcResponse *rs, const void *value, uint32_t size) {
    memcpy(rs->data + rs->data_size, value, size); rs->data_size += size;
}
int main(int argc, char **argv) {
    (void)argv;
    IpcSession session = {0};
    IpcRequest rq = {.cmd = argc > 1 ? 101 : 100};
    IpcResponse rs = {0};
    nsd_handler(&session, &rq, &rs);
    return rs.data_size != 1 || rs.data[0] != 1;
}
