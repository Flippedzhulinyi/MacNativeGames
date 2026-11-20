/* Only creation of the offline friend-service session is implemented. */
#include "ipc.h"

static void friend_handler(IpcSession *session, const IpcRequest *rq, IpcResponse *rs) {
    (void)rs;
    ipc_unimplemented(session, rq);
}

static void creator_handler(IpcSession *session, const IpcRequest *rq, IpcResponse *rs) {
    if (rq->cmd == 0) {
        rs->move[rs->nmove++] = runtime_ipc_new_session("friend:service", friend_handler, NULL, NULL);
        return;
    }
    ipc_unimplemented(session, rq);
}

__attribute__((constructor)) static void register_friends(void) {
    runtime_ipc_register("friend:u", creator_handler, NULL, NULL);
}
