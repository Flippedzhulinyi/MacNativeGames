#include <stdlib.h>
#include <string.h>
#include "../games/hogwarts/runtime/friend_service.c"

_Noreturn void ipc_unimplemented(const IpcSession *s, const IpcRequest *rq) {
    (void)s; (void)rq; exit(3);
}
void runtime_ipc_register(const char *name, IpcHandler handler, IpcOpen open, void (*close)(void *)) {
    if (strcmp(name, "friend:u") || handler != creator_handler || open || close) exit(4);
}
uint32_t runtime_ipc_new_session(const char *name, IpcHandler handler, void *state, void (*close)(void *)) {
    if (strcmp(name, "friend:service") || handler != friend_handler || state || close) exit(5);
    return 42;
}
int main(int argc, char **argv) {
    IpcSession session = {0};
    IpcRequest rq = {.cmd = 0};
    IpcResponse rs = {0};
    if (argc > 1 && !strcmp(argv[1], "unknown-creator")) rq.cmd = 1;
    creator_handler(&session, &rq, &rs);
    if (rs.nmove != 1 || rs.move[0] != 42) return 6;
    if (argc > 1 && !strcmp(argv[1], "unknown-service")) friend_handler(&session, &rq, &rs);
    return 0;
}
