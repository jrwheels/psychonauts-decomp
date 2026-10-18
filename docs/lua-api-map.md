# Lua to native registration map

Reference identity: binary-versions.md, Steam Windows only. The existing upstream
macros already model registration and stack wrappers. This session adds a
reproducible independent binary extraction rather than a second naming scheme.

`tools/native_index.py` scans the canonical mapped functions for the exact
25-byte initializer shape: frame setup, push name pointer, push registered code
pointer, ECX registration object, signed REL32 call to `0x005af520`, frame exit.
It requires 1,134 unique registrations, `.dflua` object placement, readable ASCII
names, agreement with CSV identities, and one expected implementation call for
wrapped functions. Initializer names are checked after decoding addresses;
names are not used to fabricate targets.

`build/native-index/lua-native.json` records integer `initializer_va`, `name_va`,
`object_va`, `registered_va`, `implementation_va`, `constructor_va`, plus `name`
and `stack_wrapper`. The manifest binds it to binary/CSV/tool hashes. There are
1,118 stack wrappers and 16 direct registrations. Direct registrations point to
their own native implementation, without a fictitious `_impl` address.

The constructor at `0x005af520` stores function/name/next at +0/+4/+8,
updates list head `0x0078caa4`, and increments count `0x0078caa0`.
RegisterAll at `0x005af7c0` sorts case-insensitively and calls
`lua_pushcclosure` at `0x006af810` and `lua_setglobal` at `0x006afbf0`.
Both functions already had matching upstream source; no new reconstruction
credit is claimed for them. These addresses come from bounded assembly.

| Lua name | Registered wrapper | Implementation | New native slot evidence |
| --- | --- | --- | --- |
| StopAllSounds | 0x00599330 | 0x00599390 | Sound receiver +0x198, virtual +0x58 |
| SoundSetTriggerVariable | 0x0059a2b0 | 0x0059a310 | Virtual +0xc0, DWORD/float/zero |
| SoundGetTriggerVariable | 0x0059a3d0 | 0x0059a430 | Virtual +0xc4, DWORD, x87 float return |
| SoundSetParameterControl | 0x0059a4f0 | 0x0059a550 | Virtual +0xc8, name/float/two handles |

No reachable external Lua API documentation was available during this survey.
The map establishes names and address links in this binary; it does not certify
all original scripting behavior or API equivalence across versions.
