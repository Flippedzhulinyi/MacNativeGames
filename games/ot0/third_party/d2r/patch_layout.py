"""Choose an AArch64 branch-reachable patch area for an NSO image."""

BRANCH_REACH = 1 << 27
MAX_PATCH_RESERVE = 0x2000000
PAGE_SIZE = 0x4000


def patch_layout(image_end, text_end):
    patch_after = (image_end + 0xffff) & ~0xffff
    if patch_after + MAX_PATCH_RESERVE <= BRANCH_REACH:
        return patch_after, 0, MAX_PATCH_RESERVE
    reserve = min(MAX_PATCH_RESERVE, (BRANCH_REACH - 4 - text_end) // PAGE_SIZE * PAGE_SIZE)
    if reserve <= 0:
        raise ValueError('text too large for a branch-reachable patch area')
    return -reserve, reserve, reserve
