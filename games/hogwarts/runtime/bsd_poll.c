/* Offline bsd:u has no open sockets, so every nonnegative descriptor is invalid. */
#include "ipc.h"
#include "runtime.h"
#include <limits.h>
#include <poll.h>
#include <stdint.h>
#include <string.h>

typedef struct { int32_t fd; int16_t events, revents; } GuestPollFd;
enum { GUEST_POLLNVAL = 0x20 };

void runtime_hogwarts_bsd_poll(const IpcRequest *rq, IpcResponse *rs) {
    uint32_t count = IPC_ARG(rq, uint32_t, 0);
    int32_t timeout = IPC_ARG(rq, int32_t, 4);
    if (count > INT_MAX) runtime_fail("bsd Poll: too many descriptors");
    uint64_t bytes = (uint64_t)count * sizeof(GuestPollFd);
    int32_t ready = 0;
    if (count) {
        const IpcBuffer *in = rq->na && rq->a[0].size ? &rq->a[0] :
                              rq->nx && rq->x[0].size ? &rq->x[0] : NULL;
        const IpcBuffer *out = rq->nb && rq->b[0].size ? &rq->b[0] :
                               rq->nc && rq->c[0].size ? &rq->c[0] : NULL;
        if (!in || !out || in->size < bytes || out->size < bytes)
            runtime_fail("bsd Poll: invalid descriptor buffers");
        const GuestPollFd *source = ipc_guest(in->addr, bytes);
        GuestPollFd *dest = ipc_guest(out->addr, bytes);
        memmove(dest, source, (size_t)bytes);
        for (uint32_t i = 0; i < count; i++) {
            dest[i].revents = dest[i].fd < 0 ? 0 : GUEST_POLLNVAL;
            if (dest[i].revents) ready++;
        }
        if (out == &rq->c[0]) rs->xout[rs->nxout++] = (IpcBuffer){out->addr, bytes, 0};
    }
    if (!ready && poll(NULL, 0, timeout) < 0)
        runtime_fail("bsd Poll: host wait interrupted or failed");
    uint32_t error = 0;
    IPC_OUT(rs, ready);
    IPC_OUT(rs, error);
}
