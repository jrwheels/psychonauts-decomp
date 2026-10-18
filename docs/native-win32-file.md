# Native Win32 file methods

Reference: Steam Windows 2016 PE32, SHA-1
`21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
`cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
Compiler: VC++ 2008 RTM x86, `/Od /Oy /Ob1 /Oi /MD /GS-`.

`EWin32File` is confirmed by RTTI and vtable 0x0071d8a0. Its base is EFile,
represented by the existing DiagnosticFile declaration. The handle occupies
+8; the object is 12 bytes. The native open-file counter at 0x00795a30 remains
external. These are object-level implementations, not a linked file subsystem.

| Body | Original address | Mapped bytes |
| --- | --- | ---: |
| CreateParentDirectories | 0x006a8440 | 80 |
| EWin32File constructor | 0x006a8580 | 84 |
| EWin32File scalar deleting destructor | 0x006a85e0 | 45 |
| EWin32File destructor | 0x006a8610 | 104 |
| Read | 0x006a8680 | 84 |
| Write | 0x006a86e0 | 69 |
| Seek | 0x006a8730 | 125 |
| Size | 0x006a87b0 | 75 |
| Slot +0x18: last-write FILETIME | 0x006a8800 | 55 |
| Slot +0x1c: set last-write FILETIME | 0x006a8840 | 60 |
| EFile Close | 0x006a9660 | 57 |

The constructor increments the counter and copies a nonnull filename. A null
name leaves the field at +4 untouched; no initialization was added. Destruction
releases a nonnull filename, decrements the counter, closes any nonzero handle,
clears that handle even if CloseHandle fails, then restores the base vtable.
This includes the nonzero INVALID_HANDLE_VALUE bit pattern. Close uses virtual
deletion, so derived teardown and aligned object release both run.

Read and Write return the transferred count on success and 0xffffffff on
failure. Only Read calls GetLastError on failure; the unused local preserves
that original call. Seek uses FILE_BEGIN for an unknown origin, passes a null
high-distance pointer, and does not distinguish a valid 0xffffffff result from
failure. Size saves the current position, seeks to the end, then attempts to
restore the saved position without checking any of those results.

Slot +0x18 calls GetFileTime with only the last-write output present. It returns
both FILETIME halves unchanged on success and zero on failure. Slot +0x1c
passes its two words as last-write FILETIME to SetFileTime and normalizes the
BOOL result. This establishes timestamp semantics for this implementation;
the buffered forwarders still preserve the raw EDX:EAX value. Other file
implementations and original method names remain unclaimed.

The Win32 declarations follow the existing local header's imported stdcall
pattern. API parameter meanings can be checked against Microsoft's
[GetFileTime](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfiletime)
and [SetFilePointer](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfilepointer)
documentation; the behavior above comes from the reference executable.

CreateParentDirectories recursively splits on backslashes, restores every
separator, and ignores CreateDirectoryA failures. With no separator it does
nothing, including for the first component of a relative path. Its skipLast
argument suppresses creation of the complete input path. Names are provisional.

`tools/test_native_file.py` checks 371 original/rebuilt x86 cases against
independent expected traces and state. It checks the complete fixture heap,
counter, ABI, nonvolatile registers and both timestamp halves. Close executes
the real deleting wrapper and destructor; Size executes the real Seek body.
Fixtures cover counter wrap, null name/handle, delete flags, failed close,
short/failed I/O, invalid seek origins, failed save/end/restore seeks, timestamp
failure, relative/UNC/repeated separators and ignored directory failures.
Win32 calls, CRT strrchr and filename helpers are mocked. Filename allocation
and release chains are separately covered by test_file_lifetime.py. These
checks do not establish real filesystem behavior or safe use of a null-name
object whose name field was never initialized.

The subsequent [opener/streaming continuation](native-file-streaming.md)
reconstructs 0x006a8180 and the streaming lifetime/producer methods, preserving
observed failure behavior. Streaming Read and real concurrency remain unresolved.
