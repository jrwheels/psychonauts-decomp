# Binary identities

The game was released in 2005; the available matching reference is a later
Steam Windows executable. No 2005 retail executable has been identified locally
or compared. Do not describe the Steam compiler, addresses or matches as retail
findings. Preserve upstream's target and acquire a separately identified retail
reference before attempting version comparison.

| Reference | Identity | Status |
| --- | --- | --- |
| Steam Windows depot 3831, recorded build 5757472 | SHA-256 `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`; SHA-1 `21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`; 4,150,272 bytes | Rehashed 2026-10-17; upstream matching target |
| Linux reference retained in prior inventory | SHA-256 `ec674eed6dac7045b4877dd22f36aa9088e43e58d81268c3a423273f1502d445`; 8,336,969 bytes | Historical ELF32 inventory, not rehashed this session; not the native reconstruction target |
| 2005 retail PC | Unknown | Unacquired; no coverage claims |

The Windows location is recorded in ignored `.local/reference.json`. It remains
in the owned Steam installation, read-only to this workflow. No binary is copied
into tracked files. `tools/native_index.py` verifies both Windows hashes before
address analysis and generates `build/native-index/binary.json` with sections,
all imports, exports and binary identity. `build/reference-peinfo.txt` retains
the earlier independent header/Rich-header inspection.

Windows header observations: machine `0x14c` (i386), optional-header magic
`0x10b` (PE32), image base `0x00400000`, entry `0x006ed79f`, linker 9.00.
Timestamp 2016-01-05 23:53:22 UTC is an untrusted header value, not proof of
release date. Six sections:

| Section | VA | Virtual bytes | File bytes |
| --- | --- | ---: | ---: |
| .text | 0x00401000 | 3,124,639 | 3,124,736 |
| .dfluatx | 0x006fc000 | 15,694 | 15,872 |
| .rdata | 0x00700000 | 513,074 | 513,536 |
| .data | 0x0077e000 | 98,652 | 16,384 |
| .dflua | 0x00797000 | 44,644 | 45,056 |
| .rsrc | 0x007a2000 | 433,228 | 433,664 |

There are no PE exports. Imports include MSVCR90, Direct3D9/D3DX9_40,
DirectInput8, DirectSound, XInput1_3, Bink, ISACT/AudioDrv and Steam API.
The CodeView RSDS record names `Psychonauts.pdb`; only its historical build
path survives, not a supplied PDB. The x86 exception directory is empty;
imports include `__CxxFrameHandler3`, `_except_handler3`,
`_except_handler4_common`, and the SE translator. These are evidence of available
runtime mechanisms, not proof of every function's exception model.

There is no file overlay. Ordinary code, RTTI and coherent registrations can be
read directly, and existing reconstructed code matches. This is evidence against
whole-image packing in the analyzed areas; no exhaustive packer/modification
provenance claim is made. A matching hash establishes the selected identity,
not its relationship to an untouched 2005 retail distribution.
