/* The offline diagnostic host uses the retail lp1 environment. */
#include "ipc.h"

static void nsd_handler(IpcSession *session, const IpcRequest *rq, IpcResponse *rs) {
    if (rq->cmd == 100) {
        uint8_t environment = 1; /* ServerEnvironmentType_Lp */
        IPC_OUT(rs, environment);
        return;
    }
    ipc_unimplemented(session, rq);
}

__attribute__((constructor)) static void register_nsd(void) {
    runtime_ipc_register("nsd:u", nsd_handler, NULL, NULL);
}
