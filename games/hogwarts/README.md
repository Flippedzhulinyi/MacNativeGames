# Hogwarts Legacy: experimental preparation

This is not a playable port. It checks the identities of a base NSP and an update NSP and extracts
the update's program modules into a private work folder. An optional macOS diagnostic app can launch the existing
host, but does not render a valid game picture or provide gameplay. No game content, keys or firmware are included here.
Use only files dumped from your own game and Switch; do not share the extracted files.

For a single experimental diagnostic build, with the Python dependencies and local Opus/libvpx libraries installed:

```sh
python3 games/hogwarts/scripts/build_diagnostic.py "<base>.nsp" --update "<update>.nsp" \
  -k "<prod.keys>" --work "<private work folder outside the repository>"
```

Like the Zelda build, this runs the code, data and runtime stages in order. Existing stages are reused only after
checking the inputs, the RomFS hash, each rewritten image and its structural and equivalence checks, and freshly
regenerated loader tables and their input links. A mismatch stops the build without overwriting the existing stage.
Rechecking large files and rewrites takes time. The work path may contain only ASCII letters, digits, `_`, `-`, `.`
and `/`, because it is passed to make.
This builds **only the diagnostic host**, not an app; shader tools may still need the separate command below.
It does not enable GPU submission or remove the deliberate indirect-draw stop.

After building the diagnostic host and shader tools, a **non-playable test app** can be created without copying game
data or keys into the bundle:

```sh
python3 games/hogwarts/scripts/package_diagnostic_app.py \
  --runtime "<work>/runtime/verified-tables" --output "<new diagnostic>.app"
```

The output must not already exist. Double-clicking it shows a warning before starting; the window title identifies
diagnostic mode. It forcibly disables GPU submission, skips unsupported draws, and uses an isolated profile under
`<work>/runtime/verified-tables/hogwarts-diagnostic-app-data` rather than the normal profile. Its log is
`diagnostic.log` in that directory. Subsequent launches reuse the existing directory; a file, symlink, or directory
owned by another user at that path is rejected. The private runtime, rewritten modules, RomFS and shader tools must stay in their
original locations; the bundle is not standalone. The host requires macOS 26 or later and Metal 4. It is not a
playable app or a gameplay test. The internal
`--smoke-test` argument skips the warning for automated startup checks but retains the same safety restrictions.

The observed inputs have base title ID `0100F7E00C70E000` and update metadata title ID `0100F7E00C70E800`.
The observed update filename says v65536; its version has not been independently checked in its content metadata.
The program modules are pinned by size and SHA-256 to this particular update, not by filename. Other updates are
rejected. The extractor verifies the ExeFS header, hash table and blocks, but not Nintendo RSA signatures; these checks
do not establish provenance.

With Python 3 and `cryptography`, from the repository root:

```sh
python3 games/hogwarts/scripts/prepare.py "<base>.nsp" --update "<update>.nsp" \
  --keys "<prod.keys>" --work "<private work folder outside the repository>"
```

The output is `<work>/extracted/update/{exefs,extraction-manifest.json}`. Existing output is not overwritten.
The script uses the repository's Tears of the Kingdom container parser and Bayonetta 3 update ExeFS extractor.
It does not print key values, download files, merge RomFS, rewrite modules, compile a runtime, or create an app.
Those later stages still require game-specific development and testing.

To attempt the base/update RomFS merge using the Octopath Traveler 0 merger and verify all six IVFC levels:

```sh
python3 games/hogwarts/scripts/merge_romfs.py "<base>.nsp" --update "<update>.nsp" \
  --keys "<prod.keys>" --work "<private work folder outside the repository>"
```

This rechecks the update ExeFS before merging, stages the result privately, and refuses to replace an existing
`<work>/extracted/merged-romfs`. It needs enough free space for the merged game data. It does not create an app.

To rewrite the extracted modules and run the independent structural and per-site equivalence checks, use Python with
`cryptography`, `lz4`, `capstone` and `unicorn`, plus Xcode's `llvm-objdump`:

```sh
python3 games/hogwarts/scripts/rewrite.py --work "<same private work folder>" --jobs 2
```

Each rewritten module must match the pinned digest and pass both checks before the result is published to
`<work>/rewritten/verified`. It refuses to overwrite an existing result. This stage may take several minutes and
uses several gigabytes of memory.

After both the merged RomFS and verified rewrites are available, loader tables can be generated with
`python3 games/hogwarts/scripts/prepare_runtime.py --work "<same private work folder>"`. This checks the
input hashes and rebuilds the RomFS index before publishing to `<work>/runtime/verified-tables`. It uses the
Octopath Traveler 0 table generator as a starting point and does not compile a host or generate an app. System fonts
are not configured in this diagnostic stage.

For development only, `make -C games/ot0 -f ../hogwarts/Makefile WORK="<work>/runtime/verified-tables" runtime`
compiles a diagnostic host using that game's runtime and local static Opus/libvpx libraries. It does not create an app.
For runtime shader translation it also needs `make -C games/ot0 -f ../hogwarts/Makefile
WORK="<work>/runtime/verified-tables" shader-tools`; this reuses the Octopath Traveler 0 shader tools, including its
verified prebuilt translator and pinned SPIRV-Cross source.

On the observed inputs, module mapping and a four-thread cross-module timer probe passed. The headless startup check
passed through the constructors and the beginning of `nnMain`, then deliberately stopped at focus setup; it does not
test gameplay. With the shader tools installed, a windowed diagnostic run initialized NVN, opened a window, advanced
the host's frame counter, and translated several shaders. GPU submission was disabled in those game runs, so the frame
counter does not establish that any game frame was rendered or presented. The warm-up count is not a gameplay loading
bar: in one diagnostic run, 1,711 shaders compiled and 129 failed reflection, after which the guest continued running
without a displayed frame. The diagnostic window now identifies completed warm-up and explains that GPU submission is
disabled; shader failures remain in the private diagnostic log. The graphics backend cannot yet bind a shader's dynamically
indexed texture array whose handles come from a game uniform buffer and a separate driver sampler table. The texture
builder's stencil-plane mode now uses the existing Metal stencil-view path; a standalone Metal probe checked stencil
clear and readback, but the game's rendered output has not been validated. Reflection records the observed indirect
texture and sampler arrays and checks their pairing and argument ranges. By default the shader loader rejects them:
resolving and binding those resources safely on the GPU timeline remains unimplemented. A synthetic Metal compute probe exercises the same
32-element texture and sampler array layout, dynamic indices, changed bindings and a negative control; it does not
exercise the game's replay path or prove that its texture dependencies are tracked. A bounded coherent handle snapshot
decoder is connected to diagnostic preflight, not production replay.
The Hogwarts reflection parser explicitly rejects unrecognized texture, depth-texture and sampler arrays instead of
treating them as single bindings; this is a safety check, not support for those array types.

An opt-in `HOGWARTS_SKIP_INDIRECT_DRY_RUN=1 TOTK_GPU_NOCOMMIT=1` diagnostic skips preflighted indirect draws instead
of executing them, allowing investigation beyond the first one. The host rejects this mode unless no GPU submission is
explicitly selected. The output and game state are invalid, and it cannot establish gameplay or rendering. On the observed
game inputs, a bounded run passed the first skipped draw and then stopped at an unsupported geometry shader
(NVN stage 2); other texture or sampler array types were also rejected during shader translation.
The separate `HOGWARTS_SKIP_UNSUPPORTED_STAGES_DRY_RUN=1` option, also requiring `TOTK_GPU_NOCOMMIT=1`, skips draws
using geometry or tessellation stages for further diagnostics. With both skip options, the observed run then stopped on
a fragment shader whose 2D texture handles come from a user uniform buffer rather than a direct texture slot. Neither
skip option implements the missing shader stages or indirect 2D bindings. Normal shader loading rejects the observed
fixed-offset 2D handle forms, including one where the driver and user constant banks are reversed. In the indirect dry run only, reflection validates
their pairs and argument ranges, samples coherent uniform snapshots, and probes registry resolution before skipping the
draw. The probe temporarily retains resources but does not bind or execute the shader; it cannot establish resource
lifetime or render-pass safety. Offset-aware snapshots and 2D resolver type and residency checks have synthetic tests,
including ASTC and BC7 sRGB textures. The diagnostic can also identify and skip the observed 32-element cube array;
cube-array replay remains unsupported.

For geometry research, the no-commit unsupported-stage dry run can capture the first geometry draw and its program
to a **new absolute file outside the repository**, using `HOGWARTS_GEOMETRY_CAPTURE="<private file>.plist"`.
The capture contains private game shader code and must not be shared. It refuses to overwrite an existing file.
Use `TOTK_PROFILE_DIR` to select an isolated diagnostic profile when running the host directly. To translate the
captured stages and compile them with Metal validation without submitting game work:

```sh
python3 games/hogwarts/scripts/translate_geometry_probe.py \
  --capture "<private file>.plist" --output "<new private output directory>" \
  --spirv-cross "<work>/runtime/verified-tables/build/spirv-cross/spirv-cross" --check-strip-layout
```

This reuses the repository's hash-checked XC3 geometry translator; it does not change the normal shader service or
enable geometry replay. The optional layout check accepts only non-indexed triangle strips with one geometry
invocation and writes a diagnostic `geometry_layout.json` in the private output directory. Omit the option for
other topologies. The observed first draw used a triangle strip with 32 instances. Its vertex-as-compute,
geometry-as-compute and passthrough vertex stages translated and compiled, with matching intermediate word counts.
Resource and vertex-attribute answers were defaults, not verified draw bindings; generated shaders were not executed.
The host still skips those draws, and topology remapping, GPU buffers, synchronization, hazards and draw output remain
unimplemented for Hogwarts.

An isolated synthetic Metal readback test covers a non-indexed triangle-strip remap for three and five vertices
across 32 instances, including odd-triangle winding and a deliberately incorrect expected result. The private
no-commit geometry capture also validates the remap for bounded non-indexed strip draws. The helper is not yet wired
into game rendering; indexed draws and primitive restart are rejected rather than approximated.
This test executes only synthetic shaders and does not establish that the game's geometry shader output is correct.
Another synthetic probe runs separate vertex and geometry compute encoders with the observed 13-word input and
14-word output widths, reads back every word and restart slot for 32 instances, and checks output guard regions.
The bounded allocation helper was also checked against the first private capture: one geometry invocation, three
maximum output vertices and 3/32 input vertices/instances require 4,992 / 16,128 / 1,536 bytes for vertex,
geometry and index buffers respectively. It rejects arithmetic overflow, insufficient budgets and multiple geometry
invocations. The latter are not yet safe to replay: the observed translated indexing adds the invocation to the
primitive position, which can overlap adjacent primitives. Neither the helper nor the synthetic shaders enable
game replay or prove real shader output, resource hazards, or presentation.
A separate synthetic Metal compute probe binds a 32-element cube-texture array, compares the argument buffer against
Metal's encoder, and samples indices 0, 7 and 31 before and after a binding change. Its wrong-result negative control
fails as expected. It does not execute the game's cube shader or validate replay.
With `HOGWARTS_CUBE_PREFLIGHT_ARGS=1` in the no-commit indirect dry run, the diagnostic resolves all cube textures and
samplers with temporary leases, builds their argument slots transactionally, and compares those slots with the actual
shader's Metal argument encoder. Two observed skipped draws matched for all 32 pairs; render-target relationships were
unknown, not proven safe. `HOGWARTS_CUBE_PREFLIGHT_BAD_LAYOUT=1` deliberately corrupts the encoder comparison and was
rejected. The synthetic registry probe also checks incorrect texture types, integer formats and missing samplers leave
the slots unchanged and release the temporary leases. This is diagnostic only: no game draw is submitted.
The diagnostic reflection parser also recognizes the observed 32-element 2D array form and can preflight its paired
resources with `HOGWARTS_2D_ARRAY_PREFLIGHT_ARGS=1`; `HOGWARTS_2D_ARRAY_PREFLIGHT_BAD_LAYOUT=1` is its layout negative
control. A cached game reflection and synthetic reflection rejection cases were checked, but a bounded no-commit run
did not reach a 2D-array draw, so neither its real resources nor its argument layout have been verified. A separate
synthetic 2D-array Metal probe checks dynamic sampling at indices 0, 7 and 31, changed bindings and a wrong-result
negative control; it does not execute the game's shader. The host's separate registry probe also resolves 32 synthetic
2D entries using the production registry resolver, compares the resulting slots with a Metal argument encoder, and
checks that a missing final sampler leaves the slots unchanged and releases all acquired pins.
In one no-commit run, all eight scalar pairs of the first observed shader had coherent snapshots and resolved to
registered resources. The reversed-bank pair uses the user-buffer offset from the upper packed offset and the driver
sampler from the lower offset; treating those offsets in the opposite order produced an out-of-range lookup. These
observations still do not validate actual sampling, hazards, or gameplay.
A separate synthetic Metal compute probe binds two independently resolved 2D texture/sampler pairs using a transactional
slot builder, compares the result to Metal's argument encoder, samples both textures, and swaps the bindings. A negative
control verifies the readback check. It does not execute the game's scalar shader or validate production replay.
With `HOGWARTS_SCALAR_PREFLIGHT_ARGS=1` in the no-commit indirect dry run, the same transactional builder resolves all
scalar pairs and compares their slots against the actual game shader's Metal argument encoder. An observed eight-pair
shader matched; `HOGWARTS_SCALAR_PREFLIGHT_BAD_LAYOUT=1` deliberately corrupts that comparison and was rejected.
This only checks argument IDs, not the rest of the shader's bindings or GPU execution.
The replay backend also has a conservative snapshot reader tested against its real uniform snapshot machinery; it
accepts a complete ready binding snapshot with ordered, renamed inline updates from the current submission, but
rejects earlier pending writes, GPU copies and unavailable or dropped snapshots instead of reading live memory.
A synthetic Metal 4 probe checks partially overlapping inline updates against both the decoded handles and the bytes
read from the GPU's renamed binding; it also rejects pending copies and incomplete snapshots. This does not resolve
GPU-produced handles, aliasing or actual game draws. A synthetic probe now
connects that reader to registry resolution and transactionally builds paired texture/sampler argument arrays, then
checks compute and fragment sampling; invalid snapshots, resources and layouts leave the slots unchanged. A synthetic
Metal 4 compute submission also samples the built arrays before and after texture and sampler descriptor replacement,
including replacement while the submission is gated before completion. The synthetic binding helper retains resolved
samplers and texture views and pins the backing allocations in the residency set until submission feedback. The probe
checks deferred removal, repeated pins, re-registration and rollback. The texture re-upload recycler skips allocations
already pinned by an indirect lease and discards nonresident entries; a synthetic probe checks multiple pins, deferred
removal, and reuse after the last pin, with a negative control for premature reuse. The check is not a reservation
against all forms of storage aliasing. Recycler selection and indirect pinning are serialized under the residency lock:
an allocation selected for reuse is conservatively rejected for subsequent indirect pins for the rest of that Metal
object's lifetime. A multithreaded synthetic probe races the two operations and checks that only one wins; a negative
control checks that removing the recycled-allocation guard is detected. This restriction can reject an otherwise valid
binding and is not a generation-aware implementation. In the Hogwarts host, 3D textures are now excluded from the
re-upload recycler and retired through the existing deferred-release path instead. This prevents newly recycled 3D
objects from hitting that permanent rejection; the probe checks the exclusion and detects a deliberately disabled guard.
It can increase allocation churn, and does not resolve other aliasing or lifecycle hazards. Other texture types and
other game builds retain their previous recycling behavior. The synthetic probe still holds explicit texture references;
neither aliased storage reuse nor the game's production lifetime has been validated. A probe-only branch of the production
argument encoder builds synthetic compute and fragment shaders with 32 textures, 32 samplers and a uniform binding,
and exercises Metal 4 sampling; missing resources and short snapshots are rejected without publishing an argument
buffer. Negative controls detect premature sampler release and wrong-sampler pixel errors. This encoder branch accepts
only one indirect array pair and is not enabled for game draws.
Argument-buffer sizing accounts for the complete reflected array and is
checked against a Metal argument encoder. A separate synthetic compute shader now exercises the observed 14 binding
kinds and argument IDs together: six buffer pointers, a depth texture and sampler, two typed buffers, a 2D texture and
sampler, and the 32-element texture and sampler arrays. Its argument bytes match Metal's encoder, GPU sampling matches
expected values, and swapping the typed buffers produces a detectable failure. The actual game's cached reflection
was independently checked for those 14 kinds, slots and registers. A local-only test compiled the game's cached
fragment shader and compared its own Metal argument encoder's 76 slots byte-for-byte against the synthetic bindings
in two arrangements; an intentionally swapped pair was detected. It did not execute the game's shader, supply its
real resources or validate the game's production argument builder or rendering. The synthetic shader's GPU work is
separate from the game. A preliminary registry resolver accepts only resident 3D R32Float, RGBA8Unorm or BGRA8Unorm textures and supported
samplers; its resource replacement and rejection cases have GPU probe coverage. It is not connected to game draws:
other formats, resource lifetime and render-pass hazards still need handling.
An additional opt-in isolated test executes the pinned first game fragment shader with Metal API and GPU validation,
synthetic buffers and a one-pixel render target. It checks a non-sampling branch and then samples dynamically indexed
3D textures at indices 0, 7 and 31, including changed bindings, yielding different expected pixels; intentionally
binding the wrong texture is rejected. The indirect slots are built from decoded synthetic handles.
It neither uses real game resources nor tests replay, resource lifetime or gameplay. To run it using locally generated
private cache files:

```sh
HOGWARTS_LOCAL_SHADER="<private cached shader _b.metal>" \
HOGWARTS_LOCAL_REFLECTION="<matching private _b.json>" \
python3 -m unittest discover -s tests -p test_hogwarts_indirect_texture.py
```

The draw test rejects shader bytes other than the specific observed shader, because its synthetic buffer layout and
branch conditions are tailored to that shader. The local game-derived shader is not included in this repository.
The resolver probe samples through both Metal compute and fragment stages, including after descriptor replacement;
these synthetic draws do not validate the game's replay path.
Argument-buffer and texture-slot reuse are disabled for the new indirect kinds. Store lookahead, deferred and fused
render-pass analysis now reject uncertain indirect texture dependencies conservatively.

For development, setting `HOGWARTS_INDIRECT_PREFLIGHT=1` on the Hogwarts diagnostic host permits loading an
indirect fragment shader, checks a coherent submit-time uniform snapshot, and resolves its registered textures and
samplers before deliberately aborting rather than issuing the indirect draw. On the observed game inputs this
preflight resolved all 32 texture/sampler pairs, including a BGRA8 3D texture; a standalone compute and fragment
probe checked BGRA channel sampling. The preflight also compared those 64 resolved argument slots against a fresh
Metal argument encoder for the actual game shader and resources, under the registry lock and without submitting GPU
work. The comparison passed, and deliberately corrupting a slot with `HOGWARTS_PREFLIGHT_BAD_LAYOUT=1` caused the
preflight to reject it. With `HOGWARTS_PREFLIGHT_FULL_ARGS=1`, a separate no-submission capture runs the production
argument builder's probe branch on the real shader's 14 bindings before stopping. Its 64 indirect slots matched the
preflight, and all 12 other slots were nonzero. A deliberately corrupted slot (`HOGWARTS_PREFLIGHT_BAD_FULL_ARGS=1`)
was rejected. On the observed first draw, the capture reported no missing or dummy CBUF, SBUFP, TEX, TBUF or sampler
bindings and no invalid full uniform ranges; it does not classify the C1 zero-bank case as a dummy. An opt-in negative
control (`HOGWARTS_PREFLIGHT_TEST_MISSING_TBUF=1`) removes a typed-buffer binding and checks that its dummy replacement
is reported even though its slot is nonzero. Another (`HOGWARTS_PREFLIGHT_TEST_BAD_CBUF_RANGE=1`) verifies that a
zero-length direct uniform is reported as an invalid range. The full range must resolve to the same Metal buffer,
offset and GPU address as the one-byte lookup used by the builder; a synthetic overlapping-pool test checks that a
different containing buffer is rejected. This is diagnostic only and does not change ordinary production bindings.
These checks do not prove the bound contents, resource types, physical aliasing or GPU lifetime are correct. The capture
does not bind or execute the shader and is rejected if GPU submission is enabled. Both comparisons stop before drawing
and do not establish safe production replay.
The Hogwarts backend rejects a texture descriptor when Metal cannot create its requested view instead of silently
using the base texture. A synthetic probe forces view creation failure, checks that no fallback is cached or accepted
by the indirect resolver, and checks that a later successful creation can be retried. Other game builds keep their
existing fallback behavior. This containment does not prove that the real draw can safely execute.
The indirect resolver also rejects a texture whose serial is known to be finalized, unless descriptor resolution
has followed its storage to a live replacement. In the Hogwarts build, texture finalization now holds the descriptor
registry lock across serial deletion, finalization marking and view invalidation, so resolution cannot observe the
intermediate state. Synthetic negative controls cover both an otherwise usable finalized texture and an unlocked
finalization paused between deletion and marking. This does not reserve the descriptor against changes after the lock
is released or prove safe GPU replay.
At the first indirect draw, no sampled texture had a numerically overlapping
guest range or matching serial with the current render targets. This is not a proof of disjoint physical storage:
even a non-virtual pool can have an aliased host mapping, and mappings or resources may change before encoding.
The hazard classifier therefore marks all numerically disjoint sampled/target pairs as unknown rather than safe.
With that conservative classifier, the observed first preflight reports 32 unknown sampled textures and no known
overlaps; unknown does not mean that an overlap has been observed.
A virtual-pool probe verified CPU and GPU aliasing and exercised the same hazard classifier used by the preflight
against two disjoint virtual ranges backed by the same physical page, including a test with non-virtual pool flags.
The diagnostic virtual-to-physical mapping table now
removes stale ranges on partial remap, unmap and pool finalization; a CPU/GPU alias probe covers those transitions and
rejects invalid and noncontiguous queries. It can still omit ranges if its bounded table fills, and a lookup does not
reserve the mapping against later changes, so it is not used as proof that a draw is safe. The synthetic GPU probe's wrong-sampler and premature
sampler-release negative controls also failed as expected; they do not prove the real game's resource lifetime.
The same probe checks a lock-protected diagnostic query for known overlap between partial virtual mappings and their
physical backing, including remap and unmap. An unknown result never means disjoint, and the query is not yet used to
authorize or issue game draws. The preflight copies texture and render-target ranges under the registry lock and reports
known backing overlaps after releasing it; descriptors and mappings can change between those snapshots. On the observed
first draw it reported 32 sampled textures, one target and zero known backing overlaps; this does not establish that the
32 unknown pairs are safe. Invalid address ranges are counted separately.
The preflight now counts target hazards under the same descriptor registry lock as resource resolution, after any
resource-preparation retry. A synthetic descriptor-replacement test verifies that subsequent overlap, virtual-alias
uncertainty and missing entries are reflected in the counts; the lock is released afterward, so this is not a
guarantee that the descriptors remain unchanged until a future draw. Resource resolution and hazard counting also
use the same decoded uniform snapshot per attempt; tests cover decoded IDs on success and resource failure, and ensure
an unavailable snapshot leaves the output unchanged. A pass-split retry takes a fresh snapshot.
This is not a gameplay test and does not prove that the resources remain safe
through GPU submission, aliasing, recycling or render-target hazards. The opt-in has no effect in other game builds.
The game's GPU submission is disabled by default: its completion callbacks and frame counter advance without executing
GPU work, so even the real-game preflight does not validate GPU-produced data. The separate standalone GPU probes do
submit their own synthetic work. The shared backend records previous full-game GPU driver kernel panics, so enabling
game GPU submission is hazardous and cannot by itself make this diagnostic host playable.

The experimental host initializes `nn::ro` locally and provides a `LookupSymbol` override for calls bound through the
host loader, resolving symbols against the statically mapped guest modules. It returns an explicit failure for NRO
registration and does not implement NRO loading or unloading. The
observed bounded startup called initialization but did not call registration or dynamic loading; this does not prove
those operations are unnecessary later. Its network and shop are offline and only a subset of services is implemented.
Gameplay remains unverified. Linking local Homebrew libraries may emit deployment-target warnings.

On the observed update, the main module has a 112,906,112-byte text segment. The Octopath Traveler 0 rewriter now
uses a smaller page-aligned reserve before the image when the original 32 MiB reserve would exceed the 128 MiB branch
reach. All three observed modules have passed the structural and equivalence checks; the loader, runtime and gameplay
are not yet validated. Neither a rewrite nor a verified RomFS indicates that the game can boot.
