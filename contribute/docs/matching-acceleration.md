# Optional Rust relocation decoding

The engine remains VC++ 2008 RTM x86 C++. Rust accelerates a host-side step in
the existing matcher; it does not reconstruct functions or determine matches.
Python remains the default and requires no Rust installation.

Profiling the 58-object checkpoint found 2,537,427 scalar target-decoder calls.
Repeated COFF relocation-table scans dominated the run. The optional backend
reads each function's table once and decodes its candidate addresses in Rust
batches. Byte searching, import/string checks, COMDAT handling, known-symbol
propagation, short-function anchoring and match selection remain in objmatch.
The original scalar decoder remains the comparison oracle.

## Build and use

On a Linux development host with stable Rust and its native linker installed:

```sh
mkdir -p build/rust
rustc --edition=2021 --crate-type=cdylib --crate-name=reloc_targets \
  -O -C panic=abort tools/reloc_targets.rs -o build/rust/reloc_targets.so
python3 -B -m unittest discover -s tests -v
python3 -B tools/checkbaseline.py "$REFERENCE" engine/functions.csv \
  build/game/*.obj build/lua/*.obj \
  --rust-targets build/rust/reloc_targets.so --report build/rust/comparison.json
```

There are no Cargo packages or external Rust crates. The shared library is for
the host Python process, not the 32-bit game. It stays under ignored build/.
The existing objmatch CLI accepts the same --rust-targets option. Without that
option the original Python path runs unchanged. An explicitly selected missing
or incompatible library fails rather than silently claiming acceleration.
The reference hash gate still runs before loading it in checkbaseline.py.

Rebuild the library after editing its source. The adapter checks ABI version 1;
the report records the library hash. Only trusted, locally built libraries should
be passed to ctypes. The Rust C boundary checks lengths, overflow and null
buffers; the adapter supplies the buffer storage and lifetime. Output validity
is separate from its value, so a valid zero address is preserved. REL32 and
DIR32 calculations use explicit wrapping 32-bit arithmetic. Duplicate symbol
entries retain the last valid value, exactly as the Python oracle does.

## Measured checkpoint

One unprofiled run per backend on the same machine, same 58 objects and Steam
reference SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`:

| Matching phase | Seconds |
| --- | ---: |
| Original Python | 102.074 |
| Python with relocation/code reuse | 15.072 |
| Rust batch decoding | 10.754 |

The complete batch path is 9.49x faster than the original. Relocation-table
reuse accounts for most of that gain; Rust is a further 1.40x over the cached
Python control (29% less matching time). These are local single-run matching
timings, excluding builds, PE/object loading and process startup. They do not
measure source reconstruction or gameplay performance. Tested host compiler:
rustc 1.99.1, x86_64-unknown-linux-gnu.

All three runs produce identical 3,338 object/symbol/address records, candidate
hit lists and known-symbol tables. Separately, 2,537,426 candidate pairs and
8,899,337 decoded symbol targets compare exactly. The current canonical map
still contains 3,334 unique matched functions /296,054 bytes, with no regressions.
No engine map, source or object changes are required to use the faster backend.

There are 29 tooling tests with the library built. Nine optional Rust tests
exercise signed addends, address wrap, duplicate symbols, unsupported kinds,
truncation, empty tables, FFI bounds, executable ownership and fixed-seed
differential fixtures. They skip when the optional library is absent. Other
guards check reference identity and report/output protection.

To repeat the expensive equivalence/benchmark audit after backend changes:

```sh
python3 -B tools/benchmark_matcher.py "$REFERENCE" build/game/*.obj build/lua/*.obj \
  --rust-targets build/rust/reloc_targets.so --report build/rust/benchmark.json
```

This compares against the original and cached Python paths and checks every
decoded candidate outside the timed runs. It never writes functions.csv.
Ordinary decompilation iterations only need the fast comparison and affected
tests. Exact local reports and hashes are recorded in native-verification.json.

## Contributor coverage reporting

Use `python -B contribute/tools/run_tooling_tests.py` for required Python-only synthetic
coverage, or add `--rust-targets build/rust/reloc_targets.so` to require the optional
Rust tests too. Ambient library files do not enable Rust coverage in this runner.
`native_verify.py full` uses the same separation and always runs all required
Python tooling and native differential suites. Required skips/failures, and skips
or failures in explicitly requested Rust tests, reject verification. The normal
Rust build command requires an installed host Rust compiler and native linker;
minimal Steam Deck installations may need a separately configured development
container/toolchain. A private linker shim is not a portable project dependency.
