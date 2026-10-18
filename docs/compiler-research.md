# Compiler and ABI evidence

Scope: only the Windows Steam hash in [binary-versions.md](binary-versions.md).
Reuse the established VC++ 2008 RTM x86 toolchain. Do not reinstall it or change
the upstream build system.

Direct evidence is stronger than historical guesses: the Rich header contains
218 C++ and 45 C objects associated with build 21022, linker reports 9.00,
MSVCR90 is imported, and VC++ 15.00.21022.08 with
`/Od /Ob1 /Oi /MD /GS-` reproduced the earlier baseline. Upstream 6959341 adds
`/Oy` for aligned locals; the combined build preserves every previous match
and reproduces its new functions (see native-reconstruction.md). Current flags are
`/Od /Oy /Ob1 /Oi /MD /GS-`. Mixed older/SP1
library records do not make SP1 a matching game compiler. File-level compiler
hashes live in ignored `.local/toolchain.json`. These conclusions do not apply
to the unacquired retail executable.

The preserved upstream `tools/build.sh` produces x86 COFF objects, not a linked
game. Its pipeline masks compiler exits; always use `tools/strictbuild.py` to
capture actual exits and fresh object hashes. Use the project Wine/winepath
wrappers and isolated prefix. Wine may require execution outside the command
sandbox; do not change Steam prefixes or launch the game to compile.

The native sound binding batch observes cdecl Lua functions (caller removes
arguments) and thiscall sound dispatch (ECX receiver, callee removes explicit
arguments). Float returns use x87 ST0. Microsoft's
[x86 calling-convention documentation](https://learn.microsoft.com/en-us/cpp/cpp/argument-passing-and-naming-conventions?view=msvc-170)
corroborates the conventions; the actual signature evidence is assembly and
matching objects, not modern documentation alone.

New batch-specific code-generation evidence:

* Trigger indices use FNSTCW/FLDCW, FISTP to a qword, then the low DWORD. Both
  bounds branches are unsigned (`jb`/`jae`). Keep the apparently redundant
  unsigned comparison with zero to reproduce release code.
* Setter locals are `n=-4`, float `=-8`, index `=-12`. The spelling `time`
  selects that layout; it does not establish a time unit or original name.
* The sound-handle helper needs raw handle `=-4`, name `=-8`, result `=-12`.
  A bounded six-name probe found `result` and `soundHandle` match, while
  `res`, `s`, `soundId`, `id` do not. Private source/object/assembly are preserved
  as `.local/sound-handle-layout.*`. The chosen `result` is descriptive;
  original local names remain unknown.
* The helper's signed absolute-index test preserves an INT_MIN overflow edge
  of this compiler. The reconstructed expression is not a portable ISO C++
  specification for that input; tests explicitly exclude it.

No decompiler is installed. These bodies were checked directly against bounded
Capstone assembly and upstream relocation-aware matching. Ghidra pseudocode is
not required to establish this batch and no pseudocode review is claimed.
