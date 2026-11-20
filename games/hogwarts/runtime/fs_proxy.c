/* FSP control plane adapted from games/xcx/runtime/fs_proxy.c.
   File contents remain handled by the existing local filesystem backends. */
#include "runtime.h"
#include "ipc.h"
#include <stdlib.h>

typedef struct { int initialized; uint64_t pid; } Proxy;

static void *proxy_open(void) {
    Proxy *p = calloc(1, sizeof *p);
    if (!p) runtime_fail("FSP proxy allocation");
    return p;
}

static void proxy_handler(IpcSession *session, const IpcRequest *rq, IpcResponse *rs) {
    Proxy *p = session->state;
    if (rq->cmd == 1) {
        if (!rq->has_pid || rq->data_size < 8) runtime_fail("FSP Initialize requires PID and process placeholder");
        p->pid = rq->pid;
        p->initialized = 1;
        return;
    }
    if (!p->initialized) runtime_fail("FSP request before Initialize");
    if (rq->cmd == 1005) {
        uint32_t mode = 0;
        IPC_OUT(rs, mode);
        return;
    }
    ipc_unimplemented(session, rq);
}

__attribute__((constructor)) static void register_proxy(void) {
    runtime_ipc_register("fsp-srv", proxy_handler, proxy_open, free);
}
