#pragma once
#define GUEST_ALIAS_HIGH 1
#if defined(HOGWARTS_EXPERIMENTAL)
#define GAME_TITLE_ID 0x0100f7e00c70e000ULL
#define TOTK_GAME_VERSION "experimental"
#define TOTK_GAME_DIR "hogwarts"
#else
#define GAME_OT0 1
#define GAME_TITLE_ID 0x01005270232f2000ULL
#if defined(OT0_GAME_V103)
#define TOTK_GAME_VERSION "1.0.3"
#define TOTK_GAME_DIR "v103"
#define GAME_MAX_TICK_RATE 0x25f8940
#elif defined(OT0_GAME_V104)
#define TOTK_GAME_VERSION "1.0.4"
#define TOTK_GAME_DIR "v104"
#define GAME_MAX_TICK_RATE 0x25f8940
#elif defined(OT0_GAME_V105)
#define TOTK_GAME_VERSION "1.0.5"
#define TOTK_GAME_DIR "v105"
#define GAME_MAX_TICK_RATE 0x25f8940
#else
#error "build with -DOT0_GAME_V103, -DOT0_GAME_V104 or -DOT0_GAME_V105 (the Makefile's VERSION)"
#endif
#endif
