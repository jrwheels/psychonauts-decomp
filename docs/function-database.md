# Native function database, schema 1

`engine/functions.csv` remains the upstream canonical function map. Do not
replace it. `engine/native-evidence.json` supplies version-bound curated
observations and independent verification properties. `tools/native_index.py`
validates the overlay and deterministically generates an ignored metadata index:

```sh
.venv/bin/python tools/native_index.py "$REFERENCE"
.venv/bin/python tools/native_index.py "$REFERENCE" --target-only --target 0x0059a310
```

`REFERENCE` is the path to an owned reference executable; keep any local
inventory and machine-specific paths private. Outputs are confined to ignored `build/` or `.local/`.
The full index is cached by binary, CSV, evidence, tool and dependency hashes.
Unchanged function ranges reuse validated disassembly observations when only
names/statuses/evidence change. Bump `OBSERVATION_VERSION` if their extraction
changes. Target-only mode bypasses global generation; limits are 32 functions
and 64 KiB per mapped function. No function discovery or binary rewriting occurs.

Files under `build/native-index/`:

* `manifest.json`: schema version, input hashes, output hashes and counts.
* `binary.json`: identity, architecture, image base, sections, imports/exports.
* `lua-native.json`: 1,134 registration records described in lua-api-map.md.
* `functions.json`: compact JSON array, one record per canonical CSV row.
* `target-ADDRESS.json`: optional address/size/mnemonic/operand disassembly;
  proprietary analysis remains ignored.

Every function has a stable `SHA256:RVA-eight-hex-digits` ID, full
`binary_sha256`, integer `va`, `rva`, `end_va_exclusive`, and `mapped_size`.
Address ranges are inherited from the CSV; `boundary_method` explicitly says
they have not all been revalidated as control-flow graphs. `name`, `signature`,
`calling_convention`, `parent`, `source`, `last_analysis_date` may be null.
`legacy_object` preserves old CSV provenance such as `cur/`; it is not silently
treated as a current source path.

`callees` contains direct immediate call targets with instruction `site_va`, or
null target plus `operand` for indirect calls. `callers` reverses direct calls
to mapped starts. `xrefs` contains absolute memory operands, labeled candidates;
`relevant_strings` currently contains registration names only.
`lua_registrations` links initializer VAs. `vtable_relationships` holds curated
receiver/slot/table evidence. These scans are linear within mapped ranges;
embedded data, undecodable tails, dynamic targets, pushed address constants and
tail calls can be missed or misinterpreted. They are research leads, not a
complete control-flow or data-reference analysis.

`milestones` uses independent boolean-or-null properties: `identified`,
`analyzed`, `reconstructed`, `compiled`, `behaviorally_verified`,
`binary_matched`. Null means not migrated/evaluated here; false must not mean
unknown. `csv_status` separately preserves upstream matching records. A match
does not automatically certify behavioral testing. New positive curated flags
require `evidence`; binary matching also requires `verification_method`.
`confidence` and `unresolved` retain limitations rather than inventing certainty.

Overlay root fields: `schema_version=1`, the exact `binary_sha256`, and
`functions`, keyed by canonical lowercase `0x` plus eight hex VA digits.
The Python validator checks version/identity, address membership, milestone
names/types, evidence requirements and existing relative source files. It
does not pretend to validate the truth of prose evidence. Run
`python -m unittest discover -s tests -v` for parser/guard regressions.

The database does not claim that all 10,930 functions have been analyzed or
that their original names/signatures are known. Curated counts and inherited
matching counts must be reported separately.
