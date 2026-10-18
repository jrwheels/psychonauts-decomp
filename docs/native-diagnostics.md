# Native diagnostic path

Reference: Steam PE32 SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
All new diagnostic class/function names are provisional. These are incomplete
layouts and dispatch interfaces, not recovered full class identities or sizes.
Do not instantiate them or replace the separately compiled-out `DebugPrintf`
macro in engine.h with this actual diagnostic call.

| Function | VA | Mapped bytes | Observation |
| --- | --- | ---: | --- |
| NativeDiagnostic | 0x00402300 | 49 | cdecl varargs; pointer at 0x00781fd8 gates a thiscall formatter |
| DiagnosticSink::VPrintf | 0x00402560 | 72 | 1,024-byte stack buffer, `_vsnprintf` max 1023, force buffer[1023]=0, forward |
| DiagnosticSink::Write | 0x004024d0 | 81 | Reject null/empty text; read enable byte +0x20; forward text and then newline to receiver +0x1c |
| DiagnosticStream::Write | 0x006a4ee0 | 187 | Enable byte +4; factory-open, seek-like call, byte-count write, final call; AL success from open result |

The sink global at 0x00781fd8 initially contains zero. The factory pointer at
0x00781d90 initially targets static storage at 0x00795a38. Its object storage,
construction and lifetime remain unresolved, so its declaration stays external;
no zero initializer is substituted. The stream reads a
pointer at +0x10 as the first argument to factory virtual slot +0. Arguments
are `(pointer, 0x800, 4)`. Option meanings remain unknown. The returned object
receives virtual +0x10 `(0,2)`, +0x0c `(text,strlen(text))`, and +0x04 `()`.
The source calls these Open/Seek/Write/Close for readability; only the call
order, receiver/arguments and observed returns are established. In particular,
the final method might have release/lifetime semantics beyond its provisional
Close name. No original filesystem class hierarchy or complete vtable is claimed.

Bounded immediate searches followed by instruction decoding find static
initializer `0x006fb930`: ECX=`0x00795a38`, call `0x006a88b0`, register
`0x006fbd30` through `0x006ed27b`. The latter entry supplies that same ECX to
`0x006a8ab0`. These are construction/destruction leads; the two larger native
bodies and object layout have not yet been recovered. Private evidence:
build/diagnostic-factory-storage-refs.json and the two targeted exports.

The stream returns false if disabled or if the factory returns null. Otherwise
it returns AL=1 regardless of the later virtual return values; it does not
prove all bytes were written. It performs the seek-like call before scanning
the string. A null text pointer is not guarded once open succeeds. The sink's
earlier null/empty guard is a distinct behavior, not something to silently add
to the stream. The sink appends another newline even when text already ends
with a newline. It calls the stream twice; each stream call independently opens
and finalizes its returned object.

## Compiler evidence

The direct byte-count expression compiled and passed behavioral comparison but
did not match: RTM folded the multiply-by-one and used a different intrinsic
temporary layout. An explicit local restored some layout while adding a copy.
A bounded two-form probe then compared an inline three-argument byte-count
forwarder with a templated forwarder. The former uniquely matches 0x006a4ee0;
the latter does not. The accepted source uses the small inline overload in
diagnostic.h. It reproduces the observed multiply and stack slots; it is not
proof of the original overload spelling, names, or declaration.

Probe source, COFF and assembly remain private as
`.local/diagnostic-stream-layout.*`. The earlier direct/local forms and
mismatch explanation are retained in the continuation checkpoint. No guessed
uninitialized read, inline assembly, or invented runtime behavior was added
merely to obtain a match.

## Verification scope

Subsequent RTTI work confirms the factory identity as EFileManager. Its Open
dispatcher and packed-file allocator are reconstructed in file_manager.cpp;
see native-file-manager.md. The original pointer/static-object initialization
remains external. DiagnosticFile and sink/stream names remain provisional.

`tools/test_diagnostics.py` compares original and reconstructed native bodies,
and executes the complete four-body reconstructed chain. `_vsnprintf` and the
file-factory/file virtual methods are mocked; no actual filesystem I/O occurs.
It checks varargs forwarding, cdecl/thiscall cleanup, nonvolatile registers,
zero/nonzero enable bytes, null sink/text paths, empty strings, existing newline,
non-ASCII bytes, 1022/1023-byte boundaries, forced termination, failed open,
ignored downstream failure results, and independent text/newline open calls.
AL is checked for the boolean stream return; upper EAX is not a boolean result.

A short formatter fixture initially omitted its terminating zero while expecting
short output. Both binaries correctly scanned the untouched stack bytes up to
the forced final zero. The fixture was corrected; this was not implementation
divergence. Cases deliberately simulating nontermination/error still check the
forced boundary. Mock formatting does not prove CRT format semantics, error
behavior on real inputs, actual file success, concurrency or original runtime
initialization. Oversized strings, arithmetic overflow and invalid pointers
on the enabled/successful-open path remain outside the tested domain.
