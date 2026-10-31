# Super Mario Odyssey feasibility work

This directory is an isolated feasibility branch based on the Bayonetta 3 runtime. It is not a playable port; the copied
launcher and several host services still contain Bayonetta-specific behavior.

## Target input

The original XCI is labeled 1.3.0. Its base Program NCA failed IVFC Level 5 verification. A separately provided base
NSP and update NSZ were then tested: the base NSP is title ID `0100000000010000`, version 0; the update has metadata ID
`0100000000010800`, version `393216` (displayed as 1.4.1). The local `prod.keys` is used only by extraction tools;
key values are not written to this repository.

## Progress

- The new base NSP RomFS passed all six IVFC levels (336,024 level-5 blocks). The update NSZ passed its NCA hash check,
  and its ExeFS header, hash table, and every data block passed verification.
- The merged base + v393216 update RomFS passed all six IVFC levels (346,568 level-5 blocks; 4,972 indexed files).
  The Odyssey merger accepts both supported AES-CTR-Ex table boundaries and reads the pre-map BKTR tables with normal
  AES-CTR, matching hactool's initialization path.
- The generic NSO rewriter completed for `sdk`, `subsdk0`, and `main`. Structural checks report zero violations.
  Equivalence checks covered 24,343 sites with zero divergent trials; 900 mutation controls were caught with seed 2.
- Module analysis confirmed the `rtld`, `main`, `sdk`, and `subsdk0` layout and generated analysis-only ELF files.
- Runtime tables were generated for 3 modules and 226,799 relocations. The native loader reached `nnMain`, completed
  all three module constructors, and initialized the Metal device and VI window.
- The decoded shared-font payload, display-link fallback, local performance-configuration getter, native shader
  translator, and GPU submission now pass non-activating startup probes; the latest probe rendered and presented 3,300
  frames without a runtime fault.
- HLE tracing shows `nninitStartup`, module initialization, filesystem setup, NVN device setup, and VI calls return;
  the NVN device reports ABI 55.15. The earlier shared-font and performance-configuration faults are resolved.
- Reaching the render/present loop does not yet prove the picture is a playable game scene or that controller input,
  title/menu progression, audio, and save/load work end to end. This is not yet a verified playable build.

## macOS app

Build the macOS app and extract its icon from the game image with one command:

```sh
python3 games/odyssey/build_app.py /path/to/game.nsp --update /path/to/update.nsz -k /path/to/prod.keys
```

The script prepares the verified ExeFS and merged RomFS, rewrites the v1.4.1 modules, builds the runtime and shader tools,
then packages the app. The base image and update may be the same file only when that image contains both Program NCAs;
otherwise pass the separate 1.4.1 update with `--update`. An NSZ update is hash-verified while being converted.

The game's control data supplies the required app icon. A missing image, keys file, or icon now stops the build instead
of silently producing an unbranded bundle. For XCI builds, shared fonts are extracted from the card's system update
partition. NSP builds reuse installed Ryujinx firmware when present; otherwise pass `--firmware` with an unpacked
firmware NCA directory, pass `--font-xci` with an XCI that carries the system update partition, or reuse a verified font
cache with `--shared-fonts`. A cache under `ODYSSEY_build/extracted/firmware/shared-fonts` is preferred automatically,
so later builds do not depend on the TOTK project or its cache. The result defaults to
`ODYSSEY_build/build/Super Mario Odyssey.app` beside the game image;
`--work` and `-o` override those locations. Game data remain in the work folder, while logs and writable profile data go
under `~/Library/Logs/MacNativeGames/` and `~/Library/Application Support/MacNativeGames/Odyssey/`.

Builds require macOS on Apple silicon, Xcode command line tools, Homebrew `opus` and `libvpx`, and network access the
first time the pinned SPIRV-Cross sources are prepared. This automates packaging; it does not imply gameplay verification.

Do not bypass integrity checks. The original XCI's failed RomFS was replaced by the separately supplied, verified NSP
and NSZ data. Next work is to identify the Odyssey application initialization that should populate the null object;
the public decomp repository does not expose the relevant `Application::init` implementation, so a guessed memory patch
would be unsafe.

All extracted code, RomFS data, and temporary NCA files are under the ignored `ODYSSEY_build/` directory; game data is
not intended for Git.
