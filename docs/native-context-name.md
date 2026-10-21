# Context name continuation — 2026-10-20

Reference Steam Windows SHA-1 21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07;
SHA-256 cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3.
Compiler VC++2008 RTM x86; unchanged /Od /Oy /Ob1 /Oi /MD /GS-.

ResourceContext::SetName at 0x0041f670 uniquely matches 61 bytes. It frees a
nonnull pointer at context+0x44 using (pointer, 0x1a, 1), always calls CopyFileName
with (input, 0x1a), then stores its return, including null. No self-assignment
check exists. Class/method naming and category meaning remain provisional.

All 62 sources compile strictly. Full relocation-aware comparison retains all
3358 previous addresses:3359/10930 functions, 298913/2935679 mapped bytes, zero
regressions. One map row was backed up, reviewed and promoted; report precedes
that promotion. Python/Rust targets agree. 82 context cases pass (70 regressions,
12 new), checking whole fixture heap, call order and saved-register/stack ABI.
Copy/free endpoints are mocks; alias cases prove ordering only. 29 tooling tests
pass. 61 other objects are identical apart from COFF timestamps:6056unaffected
prior cases retained, 6138 total applicable. No linked/playable engine claim.
Reports:build/context-name/;metadata: native-verification.json. No commit/push.

## Parent repository

Fetched DrDecki upstream and checked remote heads on 2026-10-20. HEAD/main
remain6959341ed94edeb17d77ad39c3b59ae5dd8f5011, already an ancestor of our
branch. No new parent commits or branches were advertised; no merge required.

## Next bounded targets

Inspected only EMesh reader 0x00435f40 and three direct dependencies using the
hash-gated reference and existing function map. Full reader remains external.
- 0x00455900(73 bytes): name setter at receiver+0. Frees nonnull old value using
  category 7/flag 1, explicitly zeros it, then copies only nonnull input using
  category 7. Resolve receiver identity before giving it a class name.
- 0x006a5de0(131 bytes): reads signed length through stream slot+8. For length<=1
  transfers that length to null and returns null; for length>1 allocates
  length bytes aligned16, transfers into the result and returns it. No explicit
  allocation-failure or terminator check. ret4 cleans an unused argument;
  inspect call sites to recover its interface before implementation.
- 0x00455610(169 bytes): constructor-like vectors+8/+60, 64-byte matrix+20,
  two member constructor calls and shared counter increment. Identity/member
  lifetime evidence unresolved; no speculative source added.

Do not repeat completed file-lifetime work or blocked constructor probes.
No ReSkate, asset, game, save or installed-state changes.
