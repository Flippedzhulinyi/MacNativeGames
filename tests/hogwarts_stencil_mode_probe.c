#include "nvn_obj.h"

int main(void) {
    tex_t texture = {0};
    view_t view = {0};
    if (nvn_sample_stencil(&texture, NULL) || nvn_sample_stencil(&texture, &view)) return 1;
    texture.stencil_mode = 1;
    if (!nvn_sample_stencil(&texture, NULL) || !nvn_sample_stencil(&texture, &view)) return 2;
    view.set_ds_mode = 1;
    if (nvn_sample_stencil(&texture, &view)) return 3;
    texture.stencil_mode = 0;
    view.set_stencil = 1;
    if (!nvn_sample_stencil(&texture, &view)) return 4;
    return 0;
}
