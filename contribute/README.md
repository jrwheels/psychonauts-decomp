# Contributing

Contributor and AI infrastructure lives here: `docs/` holds the guides, `tools/`
holds workflow helpers, and `tests/` holds their synthetic checks. These paths
are inside `contribute/`. Run all commands below from the repository root.
Core build/matching tools and native differential suites remain in the root
`tools/`; reconstruction findings and progress remain in the root `docs/` and
`engine/`. Read [agent instructions](agents.md) when using an assistant.

Contribute small, evidence-backed changes to DrDecki's existing reconstruction.
Read [README](../README.md), [native status](../docs/native-reconstruction.md), the
relevant source and [tool guide](docs/reconstruction-tools.md). The current native
engine is an object-level reconstruction, not a linked or playable replacement.
Published commits and a maintainer's uncommitted checkpoint can have different
counts: always identify the exact base commit and local changes used for a result.

## Linux and Steam Deck setup

Use Git, Python 3.10 or later with venv/pip, and a user-writable checkout whose
path contains no whitespace (the upstream build script assumes this). Python
3.10.19 and 3.13.5 are locally exercised interpreters; the CI matrix is defined separately.
On Debian/Ubuntu, the usual host prerequisites are `git python3 python3-venv
python3-pip wine` plus the distribution's 32-bit Wine support. Package names and
multilib setup vary. Check `command -v wine winepath`; both are required for
native compilation. No Wine/compiler is needed for the public synthetic tests.

On Steam Deck, use Desktop Mode and a writable checkout. Keep toolchains,
Python environments and Wine prefixes in user storage. Use an existing working
Wine installation, or a user-managed Linux development container with Wine and
its 32-bit support; configure it separately. Do not disable SteamOS read-only
protection, alter Steam compatibility settings or change game installations for
this workflow. Host and container paths must both be visible to Wine. A fresh
container/Deck installation has not been independently verified by this project.
Do not copy machine-specific Wine wrappers from another contributor.

From the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r contribute/requirements-dev.txt
python -B contribute/tools/run_tooling_tests.py
```

The manifests pin the currently tested Python packages. `requirements.txt`
contains inspection/matching dependencies; `contribute/requirements-dev.txt` adds Unicorn
and the numerical/image packages needed by synthetic reference-format tests.
The separately installable `requirements-reference.txt` supports the
[original-format research tools](../docs/reference-formats.md).
Rust is optional; see [acceleration](docs/matching-acceleration.md). The tooling
runner reports required Python coverage separately and does not run Rust tests
unless `--rust-targets` is explicitly provided. Required skips/failures fail.

## Supply your own reference

Privately supply your personally owned Steam Windows PE32 `Psychonauts.exe`:

- SHA-1: `21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`
- SHA-256: `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`

This is the supported Steam build, not the unacquired 2005 retail executable.
Never transfer its addresses/compiler conclusions to a different binary. Keep
reference files outside Git or under ignored `.local/`; never edit the reference.
Set these shell variables to your own absolute locations (do not commit them):

```sh
export REFERENCE="/path/to/owned/Psychonauts.exe"
export VC="/path/to/private/VC"
sha1sum "$REFERENCE"
sha256sum "$REFERENCE"
```

`native_index.py`, `native_verify.py` and `native_workflow.py` gate on both hashes;
`checkbaseline.py` gates on SHA-1 and records SHA-256. Reject mismatches before
address-based analysis. Do not upload the executable, original archives, extracted
assets, raw binary dumps or private analysis databases to issues, agents or CI.
Use AI tooling only with inputs you are authorized to share under its data policy;
a cloud agent does not need your game/compiler uploads to review source changes.

## Original compiler

Native matching requires privately supplied **VC++ 2008 RTM x86
15.00.21022.08**, with `bin/cl.exe`, its required companion DLLs and `include/`.
SP1 and modern compilers cannot establish matching. See the existing
[extraction instructions](../README.md#building-the-engine) for an owned original
installation medium. The repository does not distribute Microsoft's compiler.
Put your working Wine installation on PATH and use a dedicated private prefix if
needed. Initialize/configure that prefix separately with 32-bit application support;
never point it at a game Proton prefix for setup. For example, before the checks:

```sh
export PATH="/path/to/working-wine/bin:$PATH"
export WINEPREFIX="$PWD/.local/compiler-wineprefix"
```


```sh
wine "$VC/bin/cl.exe"
winepath -w "$VC/include"
python -B tools/strictbuild.py "$VC"
```

The banner must say `Version 15.00.21022.08 for 80x86`.
Keep `/Od /Oy /Ob1 /Oi /MD /GS-`. Do not change flags to obtain a match.
`strictbuild.py` audits the existing `tools/build.sh` rather than replacing it.
The upstream shell pipeline can mask failures; its exit status alone is insufficient.
Strict build replaces generated `build/game/` and `build/lua/` objects. Preserve
any development outputs you need first. The strict wrapper supports Linux/Wine;
WSL/native Windows are not verified by this contributor workflow.

## Select and claim a bounded target

Check existing issues and [claiming rules](docs/function-claims.md). Identify
canonical addresses and reference hash, source files/shared layouts, direct
callees, current blockers and why the batch supports a subsystem. Start with
one function or two to five related small functions. Do not choose unrelated
short functions just to increase totals.

```sh
python -B contribute/tools/native_workflow.py rank "$REFERENCE" --subsystem resource --out build/rank.json
python -B tools/native_index.py "$REFERENCE" --target 0x006a5670 --target-only
```

Ranking is a heuristic, not semantic evidence. Inspect the original bounded
assembly and existing callers; names and ownership remain provisional without
evidence. Keep original edge cases, member offsets, calling conventions and
attribution. Follow [AI guidance](docs/ai-contributors.md) if using an agent.
Time-box unsuccessful compiler-layout experiments and record blockers.

## Verify before requesting review

First build a baseline from your exact base and save its private report. During
development, compile only affected sources and run affected differential suites:

```sh
python -B contribute/tools/native_verify.py dev "$REFERENCE" "$VC" \
  --source src/game/resource_stream.cpp \
  --target '0x006a5670=YourProvisionalClass::YourMethod' \
  --suite test_resource_stream --out build/dev-001
```

The example target/symbol must be replaced with your actual reconstructed symbol.
Development byte compatibility cannot establish unique global matching. At the
batch boundary, run full verification into a new output directory:

```sh
python -B contribute/tools/native_verify.py full "$REFERENCE" "$VC" --out build/full-001
```

Add each proposed `--target '0xADDRESS=Demangled::Name'` for promotion review.
Full mode compiles all sources, checks all prior matching addresses and runs all
required tooling and native differential suites. It hashes inputs/objects again
after tests. All original-only cases and mocked dependencies remain explicit.
Python-only full verification is complete for required coverage; Rust coverage
is reported as not requested. To exercise Rust, build it from source and supply
`--rust-targets build/rust/reloc_targets.so`; requested Rust skips/failures fail.

A manual read-only matching check is also available:

```sh
python -B tools/checkbaseline.py "$REFERENCE" engine/functions.csv \
  build/game/*.obj build/lua/*.obj --report build/comparison.json
```

Never run `objmatch.py --write` on partial objects: it clears old matching metadata.
The workflow emits a proposal, not a CSV edit. Save the original CSV, review each
new address and preserve every prior match before changing status. Do not routinely
regenerate the whole map. Keep compiled, behavioral and matching milestones separate.

## Pull request evidence and publication

Use the PR template and standardized [result report](docs/ai-contributors.md#result-report).
Include the base commit, claimed addresses and sizes, semantic assembly observations,
exact compiler/flags, before/after matches and bytes, zero-regression evidence,
commands, test counts, mocks/exclusions and known limitations. Synthetic tests must
have independent expectations; tests that just repeat an implementation are weak
behavioral evidence. Explain missing coverage rather than claiming equivalence.

Commit only original reconstruction/tooling/docs and synthetic fixtures you are
entitled to contribute, with attribution. Preserve MIT and inherited notices.
Do not attach proprietary bytes/disassembly dumps, binaries, compiler files,
transcripts, local reports containing paths, caches or credentials. Share sanitized
summary evidence and reproducible commands; keep detailed local outputs private.

```sh
python -B contribute/tools/publication_check.py --worktree
# After manually reviewing and staging an explicit file list:
python -B contribute/tools/publication_check.py --staged
# Before publishing an approved commit range:
python -B contribute/tools/publication_check.py --history BASE..HEAD
```

See [publication safety](docs/publication-safety.md). Public CI tests synthetic
fixtures only and cannot certify game-dependent matching. A maintainer must
reproduce native evidence with privately supplied inputs before accepting a match.
Tooling-only PRs need not run native compilation unless they affect that path;
changes to verification/matching require appropriate private regressions too.
AI-assisted contributions have the same review standard as other contributions.
Do not have an agent commit, push, open issues/PRs or modify installations without
your explicit authorization. Keep each PR focused; coordinate shared-header changes.
