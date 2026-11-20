# Diagnostic host only. Run from games/ot0 with -f ../hogwarts/Makefile.
ifeq ($(strip $(WORK)),)
$(error WORK must point to the private runtime/verified-tables directory)
endif

OUT := $(WORK)/build
VOUT := $(OUT)/hogwarts
OPUS_PREFIX ?= /opt/homebrew/opt/opus
VPX_PREFIX ?= /opt/homebrew/opt/libvpx
OPT ?= -O1

GFX_SRC := $(wildcard third_party/d2r_gfx/gfx/nvn/*.c third_party/d2r_gfx/gfx/nvn/*.m third_party/d2r_gfx/gfx/nvn/*.S third_party/d2r_gfx/gfx/tex/*.c third_party/d2r_gfx/gfx/tex/*.m)
GFX_OBJECTS := $(patsubst %,$(OUT)/obj/%.o,$(GFX_SRC))
GFX_HEADERS := $(wildcard third_party/d2r_gfx/gfx/nvn/*.h third_party/d2r_gfx/gfx/nvn/include/*.h third_party/d2r_gfx/host/*.h ../hogwarts/runtime/*.h)
RUNTIME_SRC := $(filter-out runtime/frontend_ios.m,$(wildcard runtime/*.c runtime/*.m runtime/*.S)) $(wildcard ../hogwarts/runtime/*.c)
RUNTIME_HEADERS := $(wildcard runtime/*.h)
GENERATED := $(VOUT)/runtime_tables.h $(VOUT)/romfs_config.h $(VOUT)/shared_fonts_config.h

.PHONY: runtime shader-tools
runtime: $(OUT)/hogwarts-native-diagnostic

shader-tools:
	$(MAKE) -f Makefile WORK="$(WORK)" OPUS_PREFIX="$(OPUS_PREFIX)" VPX_PREFIX="$(VPX_PREFIX)" shader-tools

$(GENERATED):
	@echo "missing $@: run games/hogwarts/scripts/prepare_runtime.py" >&2; exit 1

$(OUT)/obj/%.o: % $(GFX_HEADERS) ../hogwarts/Makefile
	@mkdir -p "$(dir $@)"
	xcrun clang $(OPT) -Wall -Wextra -std=gnu11 -Wno-error -Wno-unused-function -Wno-unused-parameter -DHOGWARTS_EXPERIMENTAL \
	  -fobjc-arc -Ithird_party/d2r_gfx/gfx/nvn/include -c "$<" -o "$@"

$(OUT)/hogwarts-native-diagnostic: $(RUNTIME_SRC) $(RUNTIME_HEADERS) $(GENERATED) $(GFX_OBJECTS) ../hogwarts/Makefile
	xcrun clang -std=c11 $(OPT) -Wall -Wextra -Werror -Wno-deprecated-declarations -DHOGWARTS_EXPERIMENTAL \
	  -Iruntime -Ithird_party/d2r_gfx/gfx/nvn/include -I$(VOUT) -I$(OPUS_PREFIX)/include/opus -I$(VPX_PREFIX)/include \
	  $(RUNTIME_SRC) $(GFX_OBJECTS) $(OPUS_PREFIX)/lib/libopus.a $(VPX_PREFIX)/lib/libvpx.a \
	  -framework Metal -framework MetalFX -framework Foundation -framework QuartzCore -framework ImageIO -framework CoreGraphics \
	  -framework CoreText -framework UniformTypeIdentifiers -fobjc-arc -framework Cocoa -framework CoreVideo -framework CoreFoundation \
	  -framework AudioToolbox -framework GameController -framework CoreHaptics -framework IOKit -o "$@"
