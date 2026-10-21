> Archived native reconstruction findings. Counts and next-target lists below
> describe historical checkpoints; current state is in [native status](native-reconstruction.md).
> No raw transcripts or proprietary inputs are included.

# Reconstruction evidence

The exact Windows reference and RTM toolchain are established. Thirty-six additional native bodies are now reconstructed and verified; engine/functions.csv has individually reviewed status updates. Latest eight-body evidence, diagnostic/file-interface findings and verification limits are in native-continuation-20261017.md and native-diagnostics.md; the historical batches below remain preserved.

Existing research establishes stack-switch wrappers and registration macros (luafunc.h), typed argument helpers (luafunc.cpp), and partial original-offset class layouts (engine.h). Preserve them. README describes named-local hash ordering, temporary stack slots, /Ob1 inline expansion and float/double literal differences under RTM; use these evidence-backed hypotheses for mismatches.

`candidates.json` lists unmatched native functions of 35–130 bytes tied to existing TODO macros, using original CSV addresses as stable IDs. This is a selection inventory, not validation of purposes, dependencies or recoverable types. Avoid selecting empty debug stubs merely for counts.

Useful first related cluster for assembly inspection: SoundPauseAll (0x00599e90,39), SoundResumeAll (0x00599f20,39), SoundPauseNonMenu (0x0059a0d0,42), SoundResumeNonMenu (0x0059a280,42), then camera getters GetCameraDefaultFOV (0x005696b0,41) and GetCameraFieldOfView (0x00569610,53). Final selection depends on disassembly and unknown callees; no member offsets or native calls have been guessed.

Licensing: tools/ is MIT (DrDecki); src/lua and most psyluac retain TeCGraf Lua 4.0 COPYRIGHT and change notices. Root MIT does not automatically license proprietary assets or every reconstructed engine file. Preserve headers and do not redistribute original binaries. New local tooling extends tools/ under the existing MIT license.

Additional research: Psychonauts-Explorer and Double Fine Explorer describe asset extraction/viewing, not a matching C++ engine. PsychoPortal's GitLab page was reachable but its source/license and engine relevance were not established. Upstream also links the Psychonauts Lua API documentation. No additional code was copied.

## Batch 01 recovered bindings

| Function | Address | Mapped bytes | Evidence |
| --- | --- | ---: | --- |
| SoundPauseAll_impl | 0x00599e90 | 39 | GameApp +0x198, virtual slot +0x74 |
| SoundResumeAll_impl | 0x00599f20 | 39 | Same object, slot +0x7c |
| SoundPauseNonMenu_impl | 0x0059a0d0 | 42 | Same object, slot +0x84 |
| SoundResumeNonMenu_impl | 0x0059a280 | 42 | Same object, slot +0x88 |
| GetCameraDefaultFOV_impl | 0x005696b0 | 41 | Local float 104.0; pushes one number |

All five match with RTM flags and relocation-aware upstream objmatch. Each object body including alignment padding is 48 bytes; coverage uses canonical unpadded CSV sizes (203 total). Sound calls do not validate or read Lua arguments, and return zero. m_sound replaces only known padding at offset 0x198; other GameApp members retain their offsets. ESoundManager is a provisional name; unidentified virtual declarations are placeholders, not recovered signatures. Observed calls take no explicit arguments; return values are unused. No base class, destructor or remaining members are asserted.

## Batch 02: category pause/resume

SoundPauseCategory_impl (0x00599fb0, 188 bytes) and SoundResumeCategory_impl (0x0059a160, 188 bytes) validate exactly one argument, fetch its number, check for Lua nil, and dispatch virtual slots 0x78/0x80 on the same sound object. Nil calls LuaCallSite even though release diagnostics do not print. Pause dispatches for signed category 0–255; resume for 0–11.

The assembly uses FNSTCW/FLDCW, temporary truncation rounding and FISTP to a 64-bit stack slot, then uses the low DWORD with signed comparisons. RTM float-to-int emits an __ftol2_sse call and does not match. Conversion to unsigned int followed by storage in int reproduces the observed x87 sequence and all bytes. Source uses that explicit sequence without asserting the original category typedef or enum.

Full-object comparison: 2,877 matches, 230,395 mapped bytes, no lost addresses. The two additions contribute 376 bytes; cumulative gain 579. Twenty-eight differential emulation cases verify argument-count rejection, nil diagnostic call, fractional truncation, negative values, boundary categories 11/12/255/256, 2^31 rejection, callback this/argument, stack balance, nonvolatile registers and x87 control-word restoration. Callees are mocked; real sound behavior remains untested.

## Batch 03 findings

SoundStopCategory_impl (0x00599430, 188 bytes) shares the pause argument/conversion path and dispatches slot 0x5c. SoundMuteCategory_impl (0x00599bf0, 234 bytes) accepts one or two arguments, obtains the optional float with GetNumberArg(L,2,true), defaults to zero and passes it with the category to slot 0x64. SoundUnmuteCategory_impl (0x00599d40, 227 bytes) reads and stores that same optional argument but dispatches only the category at slot 0x6c. Preserve the discarded read; do not simplify it away. Both accept categories 0–255. Names suggesting the optional float's units are provisional.

SoundIsDolbyDigital_impl (0x0059a830, 132 bytes) requires zero arguments, tests the AL result of virtual slot 0x54, and pushes floating 1.0 or 0.0; it returns one Lua result on the valid path, zero on CheckArgs failure.

Mute/unmute initially differed solely in category/optional-float stack displacements. A six-name diagnostic (source and /FAs listing in .local/local_layout_probe.*) showed RTM assigns n=-4, category=-12, time=-8, while seconds/fadeTime/duration/fade/t instead put category=-8. Using time reproduces the observed offsets without changing control flow. Original local names are not claimed recovered. All four focused upstream byte searches hit their unique expected addresses.

Seventy-one additional original-vs-reconstructed emulator cases passed for stop/mute/unmute/Dolby paths, including missing/extra arguments, nil diagnostics, optional-number reads, default float zero, float argument bits, discarded unmute parameter, category bounds and both Dolby results. Previous 58 cases passed again after harness extension. Full regression report build/batch-03.json confirmed four new matches, 781 new bytes, and zero lost addresses. Cumulative gain: 11 native functions, 1,360 bytes.

## Batch 04: volume and attenuation

| Function | Address | Mapped bytes | Virtual slot / explicit arguments |
| --- | --- | ---: | --- |
| FXVolume_impl | 0x00599950 | 119 | 0xa0 / float volume, float zero |
| VoiceVolume_impl | 0x00599a30 | 119 | 0xa4 / float volume, float zero |
| MusicVolume_impl | 0x00599b10 | 119 | 0x9c / float volume, float zero |
| SoundSetDistanceFactor_impl | 0x0059a670 | 113 | 0xd8 / float factor |
| SoundSetRolloffFactor_impl | 0x0059a750 | 113 | 0xdc / float factor |

Each retrieves Lua's argument count, requires exactly one argument, stores GetNumberArg(L,1,false) in a float local and calls the sound interface. There is no clamping in these bindings. They return zero Lua results. Virtual slots not observed in recovered bindings remain placeholders. All five match uniquely, with a full-object regression report confirming 583 additional mapped bytes and no losses. Fifty-five differential cases verify argument rejection and preservation of float bits including negative zero, infinities and quiet NaN, plus the volume setters' explicit second float zero. Native sound implementation behavior is not inferred from mocked tests.

## Batch 05: ducking/category volume

Ducking checks one argument, evaluates its numeric nonzero comparison into an unused bool and returns zero. The release body has no engine call. The body has another identical byte hit at 0x0059b4d0, so the registration/wrapper call graph is necessary: full upstream matching associates SoundSetDucking_impl with 0x00599880, not merely an arbitrary byte search hit.

Category volume validates 2–3 arguments, uses the recovered unsigned conversion/signed range pattern, diagnoses a nil category, fetches the required volume and optional time (default float zero), and dispatches sound slot 0x94 with int/float/float. All inputs are fetched before category bounds are tested; invalid categories do not skip those helper calls. No clamping is added. RTM diagnostic assembly identifies n=-4,time=-8,categoryVolume=-12,category=-16. Original variable names are not claimed; using categoryVolume restores the actual stack layout. Saved diagnostic sources/listings are under .local/.

Fifty-nine original-vs-rebuilt emulation cases cover argument errors, nil, signed category bounds, fractional conversion, optional timing, negative zero volume and ducking comparisons with NaN/infinity. Helpers are mocked. Full-object report confirms two matches, +366 bytes and no regressions.

## Batch 06: camera-relative flags and entity echo

SoundSetCameraRelative_impl (0x0059a920,251 bytes) validates 1–2 args, interprets numeric nonzero values as booleans, defaults the second boolean to true, and uses an inline GameApp setter to update byte 0x9035 bits 6 and 7. The remaining six bits survive. The second bit's purpose is unknown and is named provisionally. RTM diagnostic shows cameraRelative=-1,n=-8,second=-9; an inlined this slot follows at -16, then three expression temporaries. This matches the original 28-byte frame.

SoundSetEcho_impl (0x0059aa80,235 bytes) validates exactly two args and calls existing GetEntityArg(L,1,false,NULL). A null entity returns before reading arg 2. For a valid entity it writes bit 2 of the DWORD at +0x64, preserving other bits. The pointer at +0x38 is checked for null, then reloaded into a separate local before sound virtual slot 0xe0 receives pointer and bool. A absent instance still permits the flag update; no sound dispatch occurs. Pointer semantics beyond being this call's instance argument are not asserted. The flags union aliases the existing m_flags, and padding replacements keep established offsets and sizes. useEcho=-1,n=-8,entity=-12,sound=-16,instance=-20 reproduce the named-local layout; original identifiers are unknown.

340 differential cases exercise accepted/rejected argument counts, nil/null entity and instance branches, positive/negative/zero/NaN comparisons, default second boolean, AL-to-32-bit arguments, writes and preservation of unrelated bits. Stack/nonvolatile/x87 checks remain active. Full comparison: two new bodies, +486 bytes, zero regressions. No direct code reuse from external research projects was needed.
