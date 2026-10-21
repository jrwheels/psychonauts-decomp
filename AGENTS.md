# Native contribution instructions

Read CONTRIBUTING.md, docs/ai-contributors.md and relevant source/evidence first.
Continue the existing project and build system. Preserve dirty work and unrelated
files. Reconstruct real C++; never patch compiler output or weaken matching.

- Only supported Steam PE32 reference SHA-1
  `21e9b89c80347c8360a8ce4b17ce45e7cd1d4a07`, SHA-256
  `cec69da17e9a5a385f88b8667f9370bf25198a12604a4c251459f68ca077a7e3`.
- Compiler: VC++ 2008 RTM x86 15.00.21022.08, `/Od /Oy /Ob1 /Oi /MD /GS-`.
- Observe layouts/ABI/ownership from evidence; names and unknown behavior stay provisional.
- Select bounded related batches; coordinate shared headers and claimed addresses.
- Use targeted development checks, then strict full verification before promotion.
- Keep every previous match. Never use objmatch --write on partial object sets.
- Add independent behavioral checks where meaningful; report mocks/exclusions.
- Required tooling tests cannot skip. Rust is optional and reported separately.
- Keep differential suites in tools/test_*.py until a verified migration is approved.
- Keep references/toolchains/analysis/reports private under ignored paths.
- No installation/save/asset changes or unrelated reconstruction unless requested.
- No automatic commits, pushes, issue/PR creation or publication.

Record blockers after a bounded experiment budget; distinguish compiled, behaviorally
verified, binary matched and game-tested. Finish with an exact file/evidence report.
