> Historical technical evidence, not the current setup/checkpoint. Use
> [CONTRIBUTING](../contribute/README.md) and [current native status](native-reconstruction.md).
> Original local report references identify private evidence, not required downloads.

# Established matching baseline

Upstream commit `2b04c7ea160b75433371b7d0fba9e548531647f3`. Its unmodified source and CSV were inspected and the baseline reproduced once before engine edits: **2,870/10,930 engine functions, 229,816/2,935,679 mapped bytes, zero regressions**. Upstream objmatch independently printed 2,870/2,875 object functions; the added read-only report confirmed every previously marked address. This baseline is established; reuse it instead of redoing setup in future sessions unless the reference, compiler or upstream changes.

Windows executable SHA-1 `21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256 `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`, size 4,150,272. Steam manifest showed completed depot 3831, build 5757472. PE i386, linker 9.00, timestamp 2016-01-05 23:53:22 UTC. Rich-header game compiler entries show build 21022 with 218 C++ and 45 C objects; mixed library entries include SP1/older tools. Header evidence alone was supplemented by matching compilation with RTM.

Matching compiler: VC++ 2008 RTM x86 15.00.21022.08, flags /Od /Ob1 /Oi /MD /GS-. All 53 upstream source files generated fresh objects. The build-script pipeline can conceal errors; strictbuild.py leaves it unchanged while capturing each compiler exit, unfiltered logs, exact version banner, object timestamps, hashes and i386 COFF validity. Latest measured progress is in progress.md.

Upstream CSV contains 10,930 mapped starts and initially 3,970 names. README reports complete 106,607-function script matching, but generated scripts are not distributed in this clone and that script total was not independently re-decompiled here. src/lua contains reconstructed runtime source; src/game contains native binding bodies, wrapper macros and partial class layouts. No Ghidra project or contribution guide was shipped. The README's 95.5% executable-identification claim was not independently remeasured; coverage here consistently uses the CSV's unpadded mapped-byte denominator.

To validate a new batch from the project root:

```sh
export PATH="$PWD/.local/bin:$PWD/.venv/bin:$PATH"
python tools/strictbuild.py "$VC"
python tools/checkbaseline.py "$REFERENCE" engine/functions.csv build/game/*.obj build/lua/*.obj --report build/new-batch.json
```

Use original tools/objmatch.py where needed for verbose diagnostics. checkbaseline.py uses its unchanged comparison implementation, gates the reference hash and reports lost/new addresses without changing the CSV. Review all new matches and preserve CSV before a targeted metadata update. Never run --write with a partial object set.

The five preexisting unmatched object symbols are: `?AddFrozen_impl@@YAHPAUlua_State@@@Z`, `?GetSaveString_impl@@YAHPAUlua_State@@@Z`, `?DumpTriggerOBBs_impl@@YAHPAUlua_State@@@Z`, `?TriggerOBB_GetAABB_impl@@YAHPAUlua_State@@@Z`, `?TriggerOBB_GetExtent_impl@@YAHPAUlua_State@@@Z`. They remain unmatched after all batches; none is newly classified or lost.
