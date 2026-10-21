# Reconstruction tool support and safety

All paths below are repository-relative. Use a writable checkout and Python
manifests from contribute/README.md. General utilities stay in the root `tools/`; their unit
tests stay in the root `tests/`. Contributor orchestration lives in
`contribute/tools/`, with its checks in `contribute/tests/`. The existing native differential suites intentionally remain
`tools/test_*.py`: verifier discovery, cross-suite imports and isolated object views
rely on those paths. A move needs demonstrated benefit and full compatibility tests.

| Utility | Supported use | Writes and limitations |
| --- | --- | --- |
| coff.py | Importable COFF reader | Reads objects; not an engine linker |
| peinfo.py | PE inventory | Read-only inspection; does not establish build compatibility |
| native_index.py | Hash-bound metadata and bounded disassembly | Writes ignored index/target files; direct-call observations are incomplete |
| native_workflow.py | Rank/plan/record attempts | Writes ignored plans; record-attempt updates evidence with backup; heuristics require review |
| native_verify.py dev | Affected-object compilation and selected suites | Writes a new ignored directory; compatibility never promotes a match |
| native_verify.py full | Strict build, complete matching and tests | Replaces generated canonical objects; writes reports/proposal; never edits CSV |
| strictbuild.py | Audit upstream build and compiler identity | Rebuilds generated objects, checks compiler exits/freshness; Linux/Wine only |
| checkbaseline.py | Reference-gated full regression comparison | Writes chosen report; protects input paths; no CSV mutation |
| objmatch.py | Existing relocation-aware matcher | Default read-only; --write clears old metadata and is excluded from routine contribution steps |
| progressmap.py | Render reviewed map | Writes requested SVG; run after reviewing map promotions |
| run_tooling_tests.py | Public synthetic tests | Optional new ignored JSON report; required skips/failures fail; Rust explicitly requested |
| publication_check.py | Stage/candidate/tree/history privacy guard | Read-only; location/rule output only; heuristic, not ownership/legal proof |
| tools/test_*.py | Private original/rebuilt native differential suites | Require owned reference and matching objects, write ignored reports; mocked services limit claims |
| reloc_targets.rs / rust_targets.py | Optional host acceleration | Build a trusted local shared library; Python remains the oracle; no engine compiler change |
| benchmark_matcher.py | Backend equivalence/performance investigation | Expensive optional private reports; unnecessary for each reconstruction batch |

Public CI needs neither the game nor Microsoft's compiler. It runs `tests/` and `contribute/tests/`, which
uses synthetic PE/COFF/byte fixtures, fake failing compilers and temporary Git repos.
It does not run native `tools/test_*.py` or certify engine equivalence.

## Separate or experimental utilities

`psydec.py`, `dec.py`, `luaast.py`, `luaformat.py`, `compare.py` and the patched Lua
compiler support the existing script workstream. `funclist.py` and `naming.py` are
analysis helpers, not native matching evidence. `psypack.py` is experimental repacking;
`psyinstall.py` writes a game installation and must never be a native setup step.
`mark.py` mutates source attribution annotations and is maintainer-only.

Private compiler-layout probes, Wine/Proton wrappers, cached databases, detailed
reports and session-export tools are not portable onboarding utilities. Cast/Studio
utilities from other branches are outside this native publication scope. Do not
merge those branches wholesale or publish local archives to satisfy dependencies.
Read-only utilities may still write reports if explicitly asked; use ignored paths.

## Platform boundaries

The exercised host is Steam Deck Linux x86_64, Python 3.10.19 and 3.13.5, with a privately
configured working Wine runtime and original compiler. Fresh distro installation,
32-bit Wine package setup, paths with whitespace, WSL and native Windows have not
been validated here. The original build script has whitespace assumptions and a
masked-error pipeline; use strictbuild and a checkout path without spaces.

## Preserved original-format research

The separate [reference-format guide](../../docs/reference-formats.md) documents the original
Psychonauts parsers, inventory/export/preview utilities, synthetic fixtures and
vendored attribution recovered from the older root checkout. They require
`requirements-reference.txt`, included by the development manifest. They are not
modding or destination-costume tools, and their results do not add native matches.
Private probes and installation scripts remain excluded from native onboarding.
